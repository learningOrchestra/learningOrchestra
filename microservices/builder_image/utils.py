from datetime import datetime
import pytz
from pymongo import MongoClient


class Database:
    def __init__(self, database_url, replica_set, database_port, database_name):
        self.mongo_client = MongoClient(
            f'{database_url}/?replicaSet={replica_set}', int(database_port))
        self.database = self.mongo_client[database_name]

    def get_filenames(self):
        return self.database.list_collection_names()

    def find_one(self, filename, query):
        file_collection = self.database[filename]
        return file_collection.find_one(query)

    def update_one(self, filename, new_value, query):
        new_values_query = {"$set": new_value}
        file_collection = self.database[filename]
        file_collection.update_one(query, new_values_query)

    def insert_one_in_file(self, filename, json_object):
        file_collection = self.database[filename]
        file_collection.insert_one(json_object)

    def delete_file(self, filename):
        file_collection = self.database[filename]
        file_collection.drop()

    @staticmethod
    def collection_database_url(database_url,
                                database_name,
                                database_filename,
                                database_replica_set
                                ):
        return f'{database_url}/{database_name}.{database_filename}' \
               f'?replicaSet={database_replica_set}&authSource=admin'

    @staticmethod
    def create_prediction_filename(parent_filename: str,
                                   classifier_name: str) -> str:
        return f'{parent_filename}{classifier_name}'


class Metadata:
    def __init__(self, database):
        self.database_connector = database
        self.timezone_london = pytz.timezone("Etc/Greenwich")

        self.metadata_document = {
            "_id": 0,
            "type": "builder/sparkml",
            "finished": False,
        }

    def create_file(self, classifier_name, train_filename, test_filename):
        london_time = datetime.now(self.timezone_london)
        now_time = london_time.strftime("%Y-%m-%dT%H:%M:%S-00:00")

        metadata = self.metadata_document.copy()
        metadata["parentDatasetName"] = [train_filename, test_filename]
        metadata["timeCreated"] = now_time
        metadata["classifier"] = classifier_name
        metadata["datasetName"] = \
            Database.create_prediction_filename(
                test_filename,
                classifier_name)

        self.database_connector.delete_file(metadata["datasetName"])
        self.database_connector.insert_one_in_file(
            metadata["datasetName"],
            metadata)

        return metadata

    def update_finished_flag(self, filename, flag):
        flag_true_query = {"finished": flag}
        metadata_file_query = {"_id": 0}
        self.database_connector.update_one(filename,
                                           flag_true_query,
                                           metadata_file_query)


class UserRequest:
    MESSAGE_INVALID_FILENAME = "invalid input dataset name"
    MESSAGE_INVALID_CLASSIFIER = "invalid classifier name"
    MESSAGE_INVALID_PREDICTION_NAME = "prediction dataset name already exists"
    MESSAGE_UNFINISHED_PROCESSING = "unfinished processing in input dataset"

    def __init__(self, database_connector):
        self.database = database_connector

    def parent_filename_validator(self, filename):
        filenames = self.database.get_filenames()

        if filename not in filenames:
            raise Exception(self.MESSAGE_INVALID_FILENAME)

    def finished_processing_validator(self, filename):
        filename_metadata_query = {"datasetName": filename}

        filename_metadata = self.database.find_one(filename,
                                                   filename_metadata_query)

        if not filename_metadata["finished"]:
            raise Exception(self.MESSAGE_UNFINISHED_PROCESSING)

    def predictions_filename_validator(self, test_filename, classifier_list):
        filenames = self.database.get_filenames()

        for classifier_name in classifier_list:
            prediction_filename = Database.create_prediction_filename(
                test_filename, classifier_name)
            if prediction_filename in filenames:
                raise Exception(self.MESSAGE_INVALID_PREDICTION_NAME)

    def model_classifiers_validator(self, classifiers_list):
        classifier_names_list = ["LR", "DT", "RF", "GB", "NB"]
        for classifier_name in classifiers_list:
            if classifier_name not in classifier_names_list:
                raise Exception(self.MESSAGE_INVALID_CLASSIFIER)
