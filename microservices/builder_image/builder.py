import pyspark.sql
from pyspark.sql import SparkSession
import time
import numpy as np  # Don't remove, the pyparsk uses the lib.
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from concurrent.futures import ThreadPoolExecutor
from utils import Metadata, Database
from pyspark.sql import dataframe
from pyspark.ml.classification import (
    LogisticRegression,
    DecisionTreeClassifier,
    RandomForestClassifier,
    GBTClassifier,
    NaiveBayes,
)


class Builder:
    METADATA_DOCUMENT_ID = 0
    DOCUMENT_ID_NAME = "_id"

    def __init__(self, database_connector: Database,
                 metadata_creator: Metadata,
                 spark_session: pyspark.sql.SparkSession):
        self.__database = database_connector
        self.__metadata_creator = metadata_creator
        self.__thread_pool = ThreadPoolExecutor()
        self.__spark_session = spark_session

    def build(self, modeling_code: str, classifiers_list: list,
              train_filename: str, test_filename: str,
              database_url_training: str, dataset_url_test: str) -> None:
        classifiers_metadata = {}

        for classifier_name in classifiers_list:
            classifiers_metadata[classifier_name] = \
                self.__metadata_creator.create_file(classifier_name,
                                                    train_filename,
                                                    test_filename)

        self.__thread_pool.submit(self.__pipeline, modeling_code,
                                  classifiers_metadata,
                                  database_url_training, dataset_url_test)

    def __pipeline(self, modeling_code: str, classifiers_metadata: dict,
                   database_url_training: str, database_url_test: str) -> None:

        (features_training, features_testing, features_evaluation) = \
            self.__modeling_code_processing(
                modeling_code,
                self.__spark_session,
                database_url_training,
                database_url_test)

        classifier_switcher = {
            "LR": LogisticRegression(),
            "DT": DecisionTreeClassifier(),
            "RF": RandomForestClassifier(),
            "GB": GBTClassifier(),
            "NB": NaiveBayes(),
        }
        classifier_threads = []

        for name, metadata in classifiers_metadata.items():
            classifier = classifier_switcher[name]
            classifier_threads.append(
                self.__thread_pool.submit(
                    self.__classifier_processing,
                    classifier,
                    features_training,
                    features_testing,
                    features_evaluation,
                    metadata,
                )
            )

        for classifier in classifier_threads:
            testing_prediction, metadata_document = classifier.result()
            self.__save_classifier_result(
                testing_prediction,
                metadata_document
            )

    def __modeling_code_processing(self,
                                   modeling_code: str,
                                   spark_session: SparkSession,
                                   database_url_training: str,
                                   database_url_test: str) -> \
            (object, object, object):

        training_df = self.__file_processor(
            database_url_training,
            spark_session)
        testing_df = self.__file_processor(
            database_url_test,
            spark_session)

        preprocessing_variables = locals()
        exec(modeling_code, globals(), preprocessing_variables)

        features_training = preprocessing_variables["features_training"]
        features_testing = preprocessing_variables["features_testing"]
        features_evaluation = preprocessing_variables["features_evaluation"]

        return features_training, features_testing, features_evaluation

    def __classifier_processing(self,
                                classifier: object,
                                features_training: dataframe,
                                features_testing: dataframe,
                                features_evaluation: dataframe,
                                metadata_document: dict
                                ) -> (object, dict):

        classifier.featuresCol = "features"

        start_fit_model_time = time.time()
        model = classifier.fit(features_training)
        end_fit_model_time = time.time()

        fit_time = end_fit_model_time - start_fit_model_time
        metadata_document["fitTime"] = fit_time

        if features_evaluation is not None:
            evaluation_prediction = model.transform(features_evaluation)

            evaluator_f1 = MulticlassClassificationEvaluator(
                labelCol="label", predictionCol="prediction", metricName="f1"
            )

            evaluator_accuracy = MulticlassClassificationEvaluator(
                labelCol="label", predictionCol="prediction",
                metricName="accuracy"
            )

            evaluation_prediction.select("label", "prediction").show()

            model_f1 = evaluator_f1.evaluate(evaluation_prediction)
            model_accuracy = evaluator_accuracy.evaluate(evaluation_prediction)

            metadata_document["F1"] = str(model_f1)
            metadata_document["accuracy"] = str(model_accuracy)

        testing_prediction = model.transform(features_testing)

        return testing_prediction, metadata_document

    def __save_classifier_result(self, predicted_df: dataframe,
                                 filename_metadata: dict) -> None:
        self.__database.update_one(
            filename_metadata["datasetName"],
            filename_metadata,
            {self.DOCUMENT_ID_NAME: self.METADATA_DOCUMENT_ID})

        document_id = 1
        for row in predicted_df.collect():
            row_dict = row.asDict()
            row_dict["_id"] = document_id
            row_dict["probability"] = row_dict["probability"].toArray().tolist()

            document_id += 1

            del row_dict["features"]
            del row_dict["rawPrediction"]

            self.__database.insert_one_in_file(filename_metadata["datasetName"],
                                               row_dict)

        self.__metadata_creator.update_finished_flag(
            filename_metadata["datasetName"], True)

    def __file_processor(self, database_url: str,
                         spark_session: SparkSession) -> dataframe:
        file = spark_session.read.format(
            "com.mongodb.spark.sql.DefaultSource").option(
            "spark.mongodb.input.uri", database_url).load()

        file_without_metadata = file.filter(
            file[self.DOCUMENT_ID_NAME] != self.METADATA_DOCUMENT_ID
        )

        metadata_fields = [
            "_id",
            "fields",
            "datasetName",
            "finished",
            "timeCreated",
            "url",
            "parentDatasetName",
            "type"
        ]
        processed_file = file_without_metadata.drop(*metadata_fields)

        return processed_file

    def __fields_from_dataframe(self, dataframe_object: dataframe,
                                is_string: bool) -> list:
        text_fields = []
        first_row = dataframe_object.first()

        if is_string:
            for column in dataframe_object.schema.names:
                if type(first_row[column]) == str:
                    text_fields.append(column)
        else:
            for column in dataframe_object.schema.names:
                if type(first_row[column]) != str:
                    text_fields.append(column)

        return text_fields
