"""
    The script handles data from sensors/states as HTTP POST request and stores
    its value into InfluxDB or additionally applies anomaly detection with 
    z-score method on sensor data.
    
    Input configuration in two files:
    - analytics_generic_sensors.json -> 
        list of generic sensors to be monitored with z-score anomaly detection
        
    - analytics_vibration_sensors.json ->
        list of vibration sensors to be monitored with z-score anomaly detection
"""
import json
import os
import math
import logging
from datetime import datetime, UTC
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import influxdb_client
from influxdb_client.client.write_api import WriteOptions
from helper import AnomalyDetectionZscore


# Set loging system
LOG_FORMAT = "%(levelname)s %(asctime)s \
    Function: %(funcName)s \
    Line: %(lineno)d \
    Message: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def get_env_var(
    env_var: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Read env variable and return its required value with log information

    Args:
        env_var (str): Name of environment variable
        req_type (str, int, float): required data type of env variable.
        default (str, int, float): will be returned if is set and env variable does not exist

    Raises:
        SystemExit: Stop program if set type_var has not passed validate
        SystemExit: Stop program if env var does not exist and default is not set
        SystemExit: Stop program if cannot convert env var variable to req_type
    """
    # set local variable. Type and value of read env variable
    env_type = type(env_var)
    env_val = os.getenv(env_var, None)

    # check if input convert type is correct or it is None (if not, return error and stop program)
    allow_convert = [str, int, float]
    if req_type not in allow_convert and req_type is not None:
        logger.error(
            "Cannot convert value of env_var %s to %s. \
                Allowed convert type: str, int, float", env_var, req_type
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env_var does not exist and we did not set default value
        logger.error("Env variable %s does not exist", env_var)
        raise SystemExit
    elif env_val is None:
        # env_var does not exist but return default (default is different than none)
        logger.warning(
            "Env variable %s does not exist, return default value: %s",
            env_var, default
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exists and it's type is diffrent as configured
        try:
            converted_env = req_type(env_val)
            logger.info(
                "Env variable %s value: %s. Converted from %s to %s.",
                env_var, env_val, env_type, req_type
            )
            return converted_env
        except Exception as e:
            logger.error(
                "Convert env_var variable %s from %s to %s failed: %s",
                env_var, env_type, req_type, e
            )
            raise SystemExit
    else:
        # env_var exists, is the same type (or we not set type)
        logger.info("Env variable %s value: %s, type: %s",
                    env_var, env_val, env_type)
        return env_val


INFLUX_HOST = get_env_var("INFLUX_HOST", str)
INFLUX_PORT = get_env_var("INFLUX_PORT", str)
INFLUX_BUCKET_NAME = get_env_var("INFLUX_BUCKET_NAME", str)
INFLUX_BATCH_SIZE = get_env_var("INFLUX_BATCH_SIZE", int)
INFLUX_FLUSH_INTERVAL = get_env_var("INFLUX_FLUSH_INTERVAL", int)
INFLUX_JITTER_INTERVAL = get_env_var("INFLUX_JITTER_INTERVAL", int)
INFLUX_ORG = get_env_var("INFLUX_ORG", str)
INFLUX_TOKEN = get_env_var("INFLUX_TOKEN", str)
INFLUX_URL = "http://" + INFLUX_HOST + ":" + INFLUX_PORT

FLASK_PORT = get_env_var("FLASK_PORT", int)

logger.info("INFLUX_URL value is:  %s", INFLUX_URL)

# Threshold for z-score value. Point above this threshold is treated as anomaly
Z_SCORE_THRESHOLD = get_env_var("Z_SCORE_THRESHOLD", float, default=2.0)

# Number of model points in list to calculate anomaly
MODEL_WINDOW_SIZE = get_env_var("MODEL_WINDOW_SIZE", int, default=25)

# Number of anomaly point in list to calculate anomaly ration
ANOMALY_LIST_SIZE = get_env_var("ANOMALY_LIST_SIZE", int, default=25)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['null'],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=['*'])

# Just simulation of MES data
production_orders = [
    {"id": 1, "order_no": 100, "product_key": "900.000.002"}
]


# key=sensor name;  value=object of class 'AnomalyDetectionZscore' for z-score anomaly detection
app.generic_analytics_objects = {}
app.vibration_analytics_objects = {}

def init_app():
    """
    Initial configuration of InfluxDB connection and 
    declaration of anomaly detection objects
    """

    # Configure connection with InfluxDB database
    try:
        logger.info("Configuring InfluxDB client ")
        app.influx_client = influxdb_client.InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, enable_gzip=False
        )

        logger.info("Configuring InfluxDB write api")
        app.write_options = WriteOptions(batch_size=INFLUX_BATCH_SIZE,
                                    flush_interval=INFLUX_FLUSH_INTERVAL,
                                    jitter_interval=INFLUX_JITTER_INTERVAL,
                                    retry_interval=1000)

    except Exception as e:
        logger.error("Configuring InfluxDB failed. Error code/reason: %s", e)


    # Get list of generic sensors for anomaly detection from JSON file
    try:
        with open("./analytics_generic_sensors.json") as file:
            generic_sensors_for_analytics = json.load(file)

            # proceed only if number of sensors not zero
            if len(generic_sensors_for_analytics["sensors"]) > 0:
                # generic sensors on which z-score anomaly detection is applied
                app.generic_sensors_for_analytics = generic_sensors_for_analytics["sensors"]
    except Exception as e:
        logger.error("Cannot open json file with generic sensor list. Result code: %s", e)


    # Create analytics objects for generic sensors
    for analytic_obj in app.generic_sensors_for_analytics:
        try:
            logger.info("Configuring z-score anomaly detection for %s", analytic_obj)
            app.generic_analytics_objects[analytic_obj] = AnomalyDetectionZscore(
                                                            analytic_obj,
                                                            MODEL_WINDOW_SIZE,
                                                            ANOMALY_LIST_SIZE,
                                                            logger
                                                            )
        except Exception as e:
            logger.error("Configuring anomaly detection for %s failed. \
                            Error code/reason: %s", analytic_obj, e)


    # Get list of vibration sensors for anomaly detection from JSON file
    try:
        with open("./analytics_vibration_sensors.json") as file:
            vibration_sensors_for_analytics = json.load(file)

            # proceed only if number of sensors not zero
            if len(vibration_sensors_for_analytics["sensors"]) > 0:
                # vibration sensors on which z-score anomaly detection is applied
                app.vibration_sensors_for_analytics = vibration_sensors_for_analytics["sensors"]
    except Exception as e:
        logger.error("Cannot open json file with generic sensor list. Result code: %s", e)


    # Create analytics objects for vibration sensors
    for analytic_obj in app.vibration_sensors_for_analytics:
        try:
            logger.info("Configuring z-score anomaly detection for %s", analytic_obj)
            app.vibration_analytics_objects[analytic_obj] = AnomalyDetectionZscore(
                                                            analytic_obj,
                                                            MODEL_WINDOW_SIZE,
                                                            ANOMALY_LIST_SIZE,
                                                            logger
                                                            )
        except Exception as e:
            logger.error("Configuring anomaly detection for %s failed. \
                          Error code/reason: %s", analytic_obj, e)


def write_to_influx(influx_measurement, influx_point):
    """
    Write data to InfluxDB database
     Args:
        influx_measurement (str): name of measurement
        influx_point (influxdb_client.Point): data point to be written to InfluxDB  
    """
    try:
        measurement = influx_measurement
        point = influx_point

        with app.influx_client.write_api(write_options=app.write_options) as write_api:
            write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

    except Exception as e:
        logger.error("Send data to InfluxDB failed. Error code/reason: %s", e)

init_app()


@app.get("/production_orders")
async def get_production_orders():
    return production_orders[0]


@app.post("/generic-state")
async def state_data(request: Request):
    """
    HTTP POST handler of data with generic state from machine
    """
    data = await request.json()

    if not data:
        return {"error": "No data provided"}, 400

    # Validate the incoming data
    try:
        state_name = data["StateName"]
        state_value = data["StateValue"]
    except Exception as e:
        logger.error("No valid state data in Json Body of HTTP POST included. \
                        Error: %s", e)

    else:
        # store data in InfluxDB
        measurement = "GenericState"
        point = (
            influxdb_client.Point(measurement)
            .tag("line_name", str(data["LineName"]))
            .tag("machine_name", str(data["MachineName"]))
            .tag("state_name", str(state_name))
            .field("value", int(state_value))
            .time(time=datetime.fromtimestamp(int(data["TimeStamp"]) / 1000, UTC),
                write_precision='ms')
        )
        write_to_influx(measurement, point)

    return {"Message": "State read successfully"}, 201


@app.post("/generic-sensor")
async def sensor_data(request: Request):
    """
    HTTP POST handler for data with generic sensor from machine
    """
    data = await request.json()

    if not data:
        return {"error": "No data provided"}, 400

    # Validate the incoming data
    try:
        sensor_name = data["SensorName"]
        sensor_value = data["SensorValue"]
    except Exception as e:
        logger.error("No valid sensor data in Json Body of HTTP POST included, error: %s", e)
    else:
        # apply z-score anomaly detection analytics on sensor data
        # and store results in InfluxDB
        if sensor_name in app.generic_sensors_for_analytics:
            logger.debug("Sensor name: %s ", sensor_name)
            app.generic_analytics_objects[sensor_name].z_score_thresh = Z_SCORE_THRESHOLD
            app.generic_analytics_objects[sensor_name].check_if_anomaly(sensor_value)
            app.generic_analytics_objects[sensor_name].calculate_anomaly_ratio()

            measurement = "SingleSensorAnalytics"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(data["LineName"]))
                .tag("machine_name", str(data["MachineName"]))
                .tag("sensor_name", str(data["SensorName"]))
                .field("value", float(round(data["SensorValue"], 4)))
                .field("anomaly", int(app.generic_analytics_objects[sensor_name].anomaly))
                .field("anomaly_ratio", round(float(app.generic_analytics_objects[sensor_name].anomaly_ratio), 4))
                .field("model_avg", round(float(app.generic_analytics_objects[sensor_name].model_avg), 4))
                .field("z_score", round(float(app.generic_analytics_objects[sensor_name].z_score), 4))
                .field("z_score_thresh", round(float(app.generic_analytics_objects[sensor_name].z_score_thresh), 4))
                .time(time=datetime.fromtimestamp(int(data["TimeStamp"]) / 1000, UTC),
                    write_precision='ms')
            )
        # only store sensor data in InfluxDB (no analytics)
        else:
            measurement = "GenericSensor"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(data["LineName"]))
                .tag("machine_name", str(data["MachineName"]))
                .tag("sensor_name", str(data["SensorName"]))
                .field("value", float(round(data["SensorValue"], 4)))
                .time(time=datetime.fromtimestamp(int(data["TimeStamp"]) / 1000, UTC),
                    write_precision='ms')
            )

        # store results in InfluxDB
        write_to_influx(measurement, point)

    # POST request successfully processed
    return {"Message": "Sensor read successfully"}, 201


@app.post("/vibration-sensor")
async def vibration_sensor_data(request: Request):
    """
    HTTP POST handler for data from vibration sensor
    """

    data = await request.json()

    if not data:
        return {"error": "No data provided"}, 400

    # Validate the incoming data
    try:
        sensor_name = data["SensorName"]
        vib_accel_tot_rms_x = data["VibAccelTotRmsX"]
        vib_accel_tot_rms_y = data["VibAccelTotRmsY"]
        vib_accel_tot_rms_z = data["VibAccelTotRmsZ"]
        logger.debug("sensor name: %s \
                    vib accel x axis: %s \
                    vib accel y axis: %s \
                    vib accel z axis: %s",
                    sensor_name, 
                    vib_accel_tot_rms_x, 
                    vib_accel_tot_rms_y, 
                    vib_accel_tot_rms_z)

    except Exception as e:
        logger.error("No valid sensor data in Json Body of HTTP POST included, error: %s", e)
    else:
        # apply z-score anomaly detection analytics on sensor data
        # and store results in InfluxDB
        if sensor_name in app.vibration_sensors_for_analytics:
            logger.debug("Sensor name: %s ", sensor_name)

            # Calculate total rms
            vib_total_rms = round(
                float(
                    math.sqrt(
                    vib_accel_tot_rms_x ** 2
                    + vib_accel_tot_rms_y ** 2
                    + vib_accel_tot_rms_z ** 2
                    )
                ),
                5,
            )
            app.vibration_analytics_objects[sensor_name].z_score_thresh = Z_SCORE_THRESHOLD
            app.vibration_analytics_objects[sensor_name].check_if_anomaly(vib_total_rms)
            app.vibration_analytics_objects[sensor_name].calculate_anomaly_ratio()

            measurement = "VibSensor"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(data["LineName"]))
                .tag("machine_name", str(data["MachineName"]))
                .tag("sensor_name", sensor_name)
                .field("vib_accel_rms_x", round(vib_accel_tot_rms_x, 4))
                .field("vib_accel_rms_y", round(vib_accel_tot_rms_y, 4))
                .field("vib_accel_rms_z", round(vib_accel_tot_rms_z, 4))
                .field("vib_accel_rms_total", round(vib_total_rms, 4))
                .field("anomaly", int(app.vibration_analytics_objects[sensor_name].anomaly))
                .field("anomaly_ratio", round(float(app.vibration_analytics_objects[sensor_name].anomaly_ratio), 4))
                .field("model_avg", round(float(app.vibration_analytics_objects[sensor_name].model_avg), 4))
                .field("z_score", round(float(app.vibration_analytics_objects[sensor_name].z_score), 4))
                .field("z_score_thresh", round(float(app.vibration_analytics_objects[sensor_name].z_score_thresh), 4))
                .time(
                    time=datetime.fromtimestamp(int(data["TimeStamp"]) / 1000, UTC),
                    write_precision="ms",
                )
            )

            # store results in InfluxDB
            write_to_influx(measurement, point)

    # POST request successfully processed
    return {"Message": "Sensor read successfully"}, 201

# Main block to run the application using Uvicorn server
if __name__ == "__main__":

    uvicorn.run("app_fastapi:app", port=FLASK_PORT, host="0.0.0.0", reload=True)
