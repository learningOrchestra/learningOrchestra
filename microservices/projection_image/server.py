from flask import jsonify, request, Flask
import os
from projection import SparkManager, MongoOperations, \
    ProjectionRequestValidator
from concurrent.futures import ThreadPoolExecutor

HTTP_STATUS_CODE_SUCCESS_CREATED = 201
HTTP_STATUS_CODE_CONFLICT = 409
HTTP_STATUS_CODE_NOT_ACCEPTABLE = 406

PROJECTION_HOST_IP = "PROJECTION_HOST_IP"
PROJECTION_HOST_PORT = "PROJECTION_HOST_PORT"

DATABASE_URL = "DATABASE_URL"
DATABASE_PORT = "DATABASE_PORT"
DATABASE_NAME = "DATABASE_NAME"
DATABASE_REPLICA_SET = "DATABASE_REPLICA_SET"

DOCUMENT_ID = "_id"
METADATA_DOCUMENT_ID = 0

MESSAGE_RESULT = "result"
PROJECTION_FILENAME_NAME = "outputDatasetName"
PARENT_FILENAME_NAME = "inputDatasetName"
FIELDS_NAME = "names"

MICROSERVICE_URI_GET = "/api/learningOrchestra/v1/transform/projection/"
MICROSERVICE_URI_GET_PARAMS = "?query={}&limit=20&skip=0"

FIRST_ARGUMENT = 0

app = Flask(__name__)
thread_pool = ThreadPoolExecutor()


@app.route("/projections", methods=["POST"])
def create_projection():
    database = MongoOperations(
        os.environ[DATABASE_URL],
        os.environ[DATABASE_REPLICA_SET],
        os.environ[DATABASE_PORT],
        os.environ[DATABASE_NAME],
    )

    request_validator = ProjectionRequestValidator(database)

    request_errors = analyse_request_errors(
        request_validator,
        request.json[PARENT_FILENAME_NAME],
        request.json[PROJECTION_FILENAME_NAME],
        request.json[FIELDS_NAME])

    if request_errors is not None:
        return request_errors

    database_url_input = MongoOperations.collection_database_url(
        os.environ[DATABASE_URL],
        os.environ[DATABASE_NAME],
        request.json[PARENT_FILENAME_NAME],
        os.environ[DATABASE_REPLICA_SET],
    )

    database_url_output = MongoOperations.collection_database_url(
        os.environ[DATABASE_URL],
        os.environ[DATABASE_NAME],
        request.json[PROJECTION_FILENAME_NAME],
        os.environ[DATABASE_REPLICA_SET],
    )

    thread_pool.submit(projection_async_processing, database_url_input,
                       database_url_output, request.json[FIELDS_NAME],
                       request.json[PARENT_FILENAME_NAME],
                       request.json[PROJECTION_FILENAME_NAME])

    return (
        jsonify({
            MESSAGE_RESULT:
                MICROSERVICE_URI_GET +
                request.json[PROJECTION_FILENAME_NAME] +
                MICROSERVICE_URI_GET_PARAMS}),
        HTTP_STATUS_CODE_SUCCESS_CREATED,
    )


def projection_async_processing(database_url_input, database_url_output,
                                projection_fields, parent_filename,
                                output_filename):
    spark_manager = SparkManager(database_url_input, database_url_output)

    spark_manager.projection(
        parent_filename, output_filename,
        projection_fields)


def analyse_request_errors(request_validator, parent_filename,
                           projection_filename, fields_name):
    try:
        request_validator.projection_filename_validator(
            projection_filename
        )
    except Exception as invalid_projection_filename:
        return (
            jsonify({MESSAGE_RESULT: invalid_projection_filename.args[
                FIRST_ARGUMENT]}),
            HTTP_STATUS_CODE_CONFLICT,
        )

    try:
        request_validator.filename_validator(parent_filename)
    except Exception as invalid_filename:
        return (
            jsonify({MESSAGE_RESULT: invalid_filename.args[FIRST_ARGUMENT]}),
            HTTP_STATUS_CODE_NOT_ACCEPTABLE,
        )

    try:
        request_validator.projection_fields_validator(
            parent_filename, fields_name
        )
    except Exception as invalid_fields:
        return (
            jsonify({MESSAGE_RESULT: invalid_fields.args[FIRST_ARGUMENT]}),
            HTTP_STATUS_CODE_NOT_ACCEPTABLE,
        )

    try:
        request_validator.finished_processing_validator(
            parent_filename)
    except Exception as unfinished_filename:
        return jsonify(
            {MESSAGE_RESULT: unfinished_filename.args[FIRST_ARGUMENT]}), \
               HTTP_STATUS_CODE_NOT_ACCEPTABLE

    return None


if __name__ == "__main__":
    app.run(
        host=os.environ[PROJECTION_HOST_IP],
        port=int(os.environ[PROJECTION_HOST_PORT])
    )
