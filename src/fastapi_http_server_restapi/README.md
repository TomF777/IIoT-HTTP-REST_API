The `app_fastapi.py` script handles data from sensors/states as HTTP POST request and stores its value into InfluxDB or additionally applies anomaly detection with z-score method on sensor data.

Input configuration in two files:
- analytics_generic_sensors.json -> 
    list of generic sensors to be monitored with z-score anomaly detection
    
- analytics_vibration_sensors.json ->
    list of vibration sensors to be monitored with z-score anomaly detection


