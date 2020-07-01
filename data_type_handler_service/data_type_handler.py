from pymongo import MongoClient


class DatabaseInterface():
    def find(self, filename, query):
        pass

    def find_one(self, filename, query):
        pass

    def get_filenames(self):
        pass

    def update_one(self, filename, new_value, query):
        pass


class RequestValidatorInterface():
    MESSAGE_INVALID_FIELDS = "invalid_fields"
    MESSAGE_INVALID_FILENAME = "invalid_filename"
    MESSAGE_MISSING_FIELDS = "missing_fields"
    STRING_TYPE = "string"
    NUMBER_TYPE = "number"

    def filename_validator(self, filename):
        pass

    def filename_validator(self, projection_filename):
        pass

    def fields_validator(self, filename, projection_fields):
        pass


class DataTypeConverterInterface():
    STRING_TYPE = "string"
    NUMBER_TYPE = "number"

    def file_converter(self, filename, fields_dictionary):
        pass


class DataTypeConverter(DataTypeConverterInterface):
    METADATA_DOCUMENT_ID = 0
    DOCUMENT_ID_NAME = "_id"

    def __init__(self, database_connector):
        self.database_connector = database_connector

    def field_converter(self, filename, field, field_type):
        query = {}
        for document in self.database_connector.find(filename, query):
            if(document[self.DOCUMENT_ID_NAME] == self.METADATA_DOCUMENT_ID):
                continue

            new_document = document

            if(field_type == self.STRING_TYPE):
                new_document[field] = str(document[field])
            elif(field_type == self.NUMBER_TYPE):
                new_document[field] = float(document[field])

            self.database_connector.update_one(
                filename, new_document, document)

    def file_converter(self, filename, fields_dictionary):
        for field in fields_dictionary:
            self.field_converter(
                filename, field, fields_dictionary[field])


class MongoOperations(DatabaseInterface):
    def __init__(self, database_url, database_port, database_name):
        self.mongo_client = MongoClient(
            database_url,
            int(database_port))
        self.database = self.mongo_client[database_name]

    def find(self, filename, query):
        file_collection = self.database[filename]
        return file_collection.find(query)

    def get_filenames(self):
        return self.database.list_collection_names()

    def update_one(self, filename, new_value, query):
        file_collection = self.database[filename]
        file_collection.update_one(new_value, query)

    def find_one(self, filename, query):
        file_collection = self.database[filename]
        return file_collection.find_one(query)


class DataTypeHandlerRequestValidator(RequestValidatorInterface):
    def __init__(self, database_connector):
        self.database = database_connector

    def filename_validator(self, filename):
        filenames = self.database.get_filenames()

        if(filename not in filenames):
            raise Exception(self.MESSAGE_INVALID_FILENAME)

    def fields_validator(self, filename, fields):
        if not fields:
            raise Exception(self.MESSAGE_MISSING_FIELDS)

        filename_metadata_query = {"filename": filename}

        filename_metadata = self.database.find_one(
            filename, filename_metadata_query)

        for field in fields:
            if field not in filename_metadata["fields"]:
                raise Exception(self.MESSAGE_INVALID_FIELDS)

            if(fields[field] != self.NUMBER_TYPE and
               fields[field] != self.STRING_TYPE):
                raise Exception(self.MESSAGE_INVALID_FIELDS)