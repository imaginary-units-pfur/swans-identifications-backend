from flask import Flask, request, send_from_directory, url_for

from main import process_files
from flask_cors import CORS
import db
import os
import uuid
import fnmatch

from logging.config import dictConfig

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)

app = Flask("swans-identification-backend")
CORS(app)
app.config["IMAGES_TO_PROCESS"] = "images/to_process/"
app.config["SAVED_IMAGES"] = "images/saved/"


@app.route("/analyze", methods=["POST"])
def analyze():
    paths = []
    app.logger.info(f"Got files {[x.filename for x in request.files.getlist('f[]')]}")
    for file in request.files.getlist("f[]"):
        if file and file.filename:
            file_name_stored = os.path.join(
                app.config["IMAGES_TO_PROCESS"], file.filename
            )
            file.save(file_name_stored)
            paths.append(file_name_stored)

    app.logger.info(f"Seinding paths to model {paths}")
    output = process_files(paths)
    formatted_output = {}
    for analysis in output:
        filename = analysis.pop("filename")
        formatted_output[filename] = {"overall_class": analysis}

    for path in paths:
        os.remove(path)

    return formatted_output


@app.route("/save", methods=["POST"])
def save():
    app.logger.info(f"Got files {[x.filename for x in request.files.getlist('f[]')]}")

    tags = request.files["tags"].read().decode("utf-8").strip().split(" ")
    app.logger.info(f"Got tags {tags}")

    for file in request.files.getlist("f[]"):
        if file and file.filename and file.filename != "tags":
            file_uuid = str(uuid.uuid4())
            ext = file.filename.split(".")[-1]
            file_name_stored = os.path.join(
                app.config["SAVED_IMAGES"], f"{file_uuid}.{ext}"
            )
            file.save(file_name_stored)
            db.add_image(file_uuid, file.filename, tags)

            resp = {"status": "success", "uuid": file_uuid}
            return resp, 200

    resp = {"status": "internal server error"}
    return resp, 500


@app.route("/image", methods=["GET"])
def get_image_by_tags():
    tags = request.args["tags"].split(" ")
    app.logger.info(f"Got tags {tags}")

    img_uuids = db.get_by_tags(tags)

    output = []
    for img_uuid in img_uuids:
        data = dict()
        data["filename"] = db.get_filename(img_uuid)
        data["uuid"] = img_uuid
        data["tags"] = db.get_tags(img_uuid)
        data["download"] = url_for("download", uuid=img_uuid)
        data["update"] = url_for("update", uuid=img_uuid)
        data["delete"] = url_for("delete", uuid=img_uuid)
        output.append(data)

    return output


@app.route("/download/<uuid>", methods=["GET"])
def download(uuid):
    path = find_saved_image(uuid)
    if path is not None:
        return send_from_directory(app.config["SAVED_IMAGES"], os.path.basename(path))
    else:
        resp = {"status": "not found"}
        return resp, 404


def find_saved_image(uuid):
    pattern = f"{uuid}.*"
    for root, _, files in os.walk(app.config["SAVED_IMAGES"]):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                return os.path.join(root, name)


@app.route("/update/<uuid>", methods=["POST"])
def update(uuid):
    app.logger.info(f"Updating {uuid}")

    tags = request.files["tags"].read().decode("utf-8").strip().split(" ")
    app.logger.info(f"Got new tags {tags}")
    db.update(uuid, tags)

    resp = {"status": "success"}
    return resp, 200


@app.route("/delete/<uuid>", methods=["POST"])
def delete(uuid):
    db.delete_by_uuid(uuid)

    path = find_saved_image(uuid)
    if path is not None:
        os.remove(path)

    resp = {"status": "success"}
    return resp, 200


if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
