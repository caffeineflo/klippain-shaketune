# Shake&Tune: 3D printer analysis tools
#
# Copyright (C) 2024 Félix Boisselier <felix@fboisselier.fr> (Frix_x on Discord)
# Licensed under the GNU General Public License v3.0 (GPL-3.0)

import requests
from ..helpers.console_output import ConsoleOutput
from ..shaketune_process import ShakeTuneProcess
from .accelerometer import Accelerometer

def axes_shaper_calibration_web(gcmd, config, st_process: ShakeTuneProcess) -> None:
    # Get webservice URL parameter
    webservice_url = gcmd.get('URL', default='http://localhost:5000')
    webservice_url = webservice_url.rstrip('/')  # Remove trailing slash if present
    
    # Get parameters with validation
    axis = gcmd.get('AXIS', default='x').lower()
    if axis not in ['x', 'y', 'both']:
        raise gcmd.error("Incorrect AXIS parameter. Valid choices are: X, Y, BOTH")
    
    max_smoothing = gcmd.get_float('MAX_SMOOTHING', default=None)
    accel_chip = gcmd.get('ACCEL_CHIP', None)
    raw_name = gcmd.get('RAW_NAME', None)
    skip_x = gcmd.get_int('SKIP_X', 0)
    skip_y = gcmd.get_int('SKIP_Y', 0)

    printer = config.get_printer()
    
    # Find and validate accelerometer
    if accel_chip is None:
        accel_chip = Accelerometer.find_axis_accelerometer(printer, axis)
    k_accelerometer = printer.lookup_object(accel_chip, None)
    if k_accelerometer is None:
        raise gcmd.error("No valid accelerometer found!")
    
    # Initialize accelerometer
    accelerometer = Accelerometer(printer.get_reactor(), k_accelerometer)
    
    # Perform the test movements and data collection
    if axis == 'both':
        if skip_x == 0:
            ConsoleOutput.print("Testing X axis")
            accelerometer.start_measurement()
            accelerometer.stop_measurement('shaper_calibrate_x', append_time=True)
        if skip_y == 0:
            ConsoleOutput.print("Testing Y axis")
            accelerometer.start_measurement()
            accelerometer.stop_measurement('shaper_calibrate_y', append_time=True)
    else:
        ConsoleOutput.print(f"Testing {axis.upper()} axis")
        accelerometer.start_measurement()
        accelerometer.stop_measurement(f'shaper_calibrate_{axis}', append_time=True)

    # Wait for data collection to complete
    accelerometer.wait_for_file_writes()

    # Get the collected data files
    data_files = []
    if axis == 'both':
        if skip_x == 0:
            data_files.append(('shaper_calibrate_x', accelerometer.get_latest_data_file('shaper_calibrate_x')))
        if skip_y == 0:
            data_files.append(('shaper_calibrate_y', accelerometer.get_latest_data_file('shaper_calibrate_y')))
    else:
        data_files.append((f'shaper_calibrate_{axis}', accelerometer.get_latest_data_file(f'shaper_calibrate_{axis}')))

    # Upload data and get results
    ConsoleOutput.print("Uploading data for processing...")
    for test_name, filepath in data_files:
        try:
            with open(filepath, 'rb') as f:
                response = requests.post(
                    f'{webservice_url}/process/shaper',
                    files={'file': (f'{test_name}.csv', f)}
                )
                response.raise_for_status()
                
                # Save the returned graph
                with open(f'/tmp/{test_name}_result.png', 'wb') as f:
                    f.write(response.content)
                
                ConsoleOutput.print(f"Results for {test_name} saved to: /tmp/{test_name}_result.png")
                
        except requests.exceptions.RequestException as e:
            raise gcmd.error(f"Failed to process data: {str(e)}")
        except IOError as e:
            raise gcmd.error(f"Failed to save results: {str(e)}")

    ConsoleOutput.print("Shaper calibration complete!")
