import statistics

class AnomalyDetectionZscore:
    """
        Analyse real-time data from electrical device
        and apply z-score algorithm to detect anomalies

        model_data          list where real-time (non anomalous) data are stored
        model_size          definition how many data points should be in `model_data`
        anomaly_list        list with anomaly detection results (1 and 0)
        anomaly_list_size  definition how many data points should be in `anomaly_list`
        anomaly_ratio       percentage of anomalous data in `anomaly_list`
        anomaly             result if current data point is anomaly (1) or not (0)
        model_avg           avarage mean of `model_data`
        model_std_dev       standard deviation of `model_data`
        z_score             calculated z-score value for single sensor data
        z_score_thresh      threshold above which sensor data is interpeted as anomalous
        name                name of the object/sensor on which the algorithm is applied
    """

    def __init__(self, name: str,
                 model_size: int, 
                 anomaly_list_size: int, 
                 logger) -> None:
        self._model_data = []
        self._model_size = model_size
        self._anomaly_list = []
        self._anomaly_list_size = anomaly_list_size
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0
        self._z_score_thresh = 0.0
        self._name = name
        self._logger = logger

    # Read only wariables
    @property
    def anomaly(self) -> int:
        """return 1 if data point is anmaly, 0 else"""
        return self._anomaly

    @property
    def model_avg(self) -> float:
        """return Mean of sensor data from given data model"""
        return self._model_avg

    @property
    def model_std_dev(self) -> float:
        """return Std Dev of sensor data from given data model"""
        return self._model_std_dev

    @property
    def z_score(self) -> float:
        """return calculated z-score value for given sensor data point"""
        return self._z_score

    @property
    def anomaly_ratio(self) -> float:
        """return anomaly ratio in real-time data"""
        return self._anomaly_ratio

    @property
    def model_completeness(self) -> int:
        """return percentage of data model"""
        return int(100 * len(self._model_data) / self._model_size)

    @property
    def z_score_thresh(self) -> float:
        """return z-score threshold value"""
        return self._z_score_thresh

    @z_score_thresh.setter
    def z_score_thresh(self, z_score_threshold: float):
        if z_score_threshold == 0:
            logger.error("Z-score threshold must be above zero")
            self._z_score_thresh = 2.0
        else:
            self._z_score_thresh = z_score_threshold

    def reset_algorithm(self) -> bool:
        """Reset data model in algorithm"""

        self._model_data = []
        self._anomaly_list = []
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0

    def is_model_complete(self) -> bool:
        """Return True if data model has enough data points"""
        return True if len(self._model_data) == self._model_size else False

    def calculate_anomaly_ratio(self):
        """Sum all anomalies results (0 and 1) from `anomaly_list`
           and divide it by the size of the list

        Args:
            anomaly_list_size (int): size of anomaly list to calculate ratio
        """

        try:
            if self.is_model_complete():
                if len(self._anomaly_list) < self._anomaly_list_size:
                    self._anomaly_list.append(self._anomaly)
                else:
                    self._anomaly_list.pop(0)
                    self._anomaly_list.append(self._anomaly)
                    self._anomaly_ratio = round(sum(self._anomaly_list) / self._anomaly_list_size, 3)
        except Exception as e:
            logger.error(
                f"Calculation `anomaly ratio of model` {self._name} failed. Error code/reason: {e}"
            )

    def check_if_anomaly(self, value: float):
        """
        Z-score algorithm to check if argument value is anomaly or not.

        Args:
            value (any): input value (sensor data) to be evaluated by algorithm
        """

        try:
            if self.is_model_complete():
                # recalculate the avg and std dev using only data points which are not anomaly
                self._model_avg = round(abs(statistics.mean(self._model_data)), 3)
                self._model_std_dev = abs(statistics.stdev(self._model_data))

                # avoid division by zero
                if self._model_std_dev == 0:
                    self._model_std_dev = 0.001
                self._z_score = round((abs(value) - self._model_avg) / self._model_std_dev, 3)

                # Check if new point is beyond z-score threshold i.e. this is anomaly
                if abs(self._z_score) > self.z_score_thresh:
                    # If anomaly, do not add to the model_data
                    self._anomaly = 1
                else:
                    # If not anomaly, add this point to data model
                    # and delete the 1st point (moving window)
                    self._model_data.pop(0)
                    self._model_data.append(value)
                    self._anomaly = 0

            else:
                # build data model by appending incoming sensor data to the list `model_data`
                self._model_data.append(value)

        except Exception as e:
            logger.error(
                f'Calculation `anomaly of model` "{self._name}" failed. Error code/reason: {e}'
            )