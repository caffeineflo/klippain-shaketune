# Shake&Tune: 3D printer analysis tools
#
# Copyright (C) 2024 Félix Boisselier <felix@fboisselier.fr> (Frix_x on Discord)
# Licensed under the GNU General Public License v3.0 (GPL-3.0)

import math
import requests
from ..helpers.console_output import ConsoleOutput
from ..shaketune_process import ShakeTuneProcess
from .accelerometer import Accelerometer

MIN_SPEED = 2  # mm/s

def create_vibrations_profile_web(gcmd, config, st_process: ShakeTuneProcess) -> None:
    # Get webservice URL parameter
    webservice_url = gcmd.get('URL', default='http://localhost:5000')
    webservice_url = webservice_url.rstrip('/')  # Remove trailing slash if present
    
    printer = config.get_printer()
    toolhead = printer.lookup_object('toolhead')
    systime = printer.get_reactor().monotonic()

    # Get parameters with validation
    accel = gcmd.get_float('ACCEL', default=3000.0, minval=100.0)
    feedrate = gcmd.get_float('VELOCITY', default=100.0, minval=20.0)
    z_height = gcmd.get_float('Z_HEIGHT', default=20.0, minval=1.0)
    feedrate_travel = gcmd.get_float('TRAVEL_SPEED', default=120.0, minval=20.0)

    # Find and validate accelerometer
    accel_chip = Accelerometer.find_axis_accelerometer(printer, 'xy')
    k_accelerometer = printer.lookup_object(accel_chip, None)
    if k_accelerometer is None:
        raise gcmd.error('No suitable accelerometer found for measurement!')
    accelerometer = Accelerometer(printer.get_reactor(), k_accelerometer)

    # Save and update acceleration settings
    toolhead_info = toolhead.get_status(systime)
    old_accel = toolhead_info['max_accel']
    old_sqv = toolhead_info['square_corner_velocity']
    if 'minimum_cruise_ratio' in toolhead_info:
        old_mcr = toolhead_info['minimum_cruise_ratio']
        gcode.run_script_from_command(
            f'SET_VELOCITY_LIMIT ACCEL={accel} MINIMUM_CRUISE_RATIO=0 SQUARE_CORNER_VELOCITY=5.0'
        )
    else:
        old_mcr = None
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={accel} SQUARE_CORNER_VELOCITY=5.0')

    # Disable input shaper if active
    input_shaper = printer.lookup_object('input_shaper', None)
    if input_shaper is not None:
        input_shaper.disable_shaping()

    # Calculate movement coordinates
    kin_info = toolhead.kin.get_status(systime)
    x_min = kin_info['axis_minimum'].x
    x_max = kin_info['axis_maximum'].x
    y_min = kin_info['axis_minimum'].y
    y_max = kin_info['axis_maximum'].y
    _, _, _, E = toolhead.get_position()

    # Move to start position
    toolhead.move([x_min, y_min, z_height, E], feedrate_travel)
    toolhead.dwell(0.5)

    # Start measurement and perform movements
    accelerometer.start_measurement()
    toolhead.dwell(0.5)

    # Perform the test pattern
    toolhead.move([x_max, y_min, z_height, E], feedrate)
    toolhead.move([x_max, y_max, z_height, E], feedrate)
    toolhead.move([x_min, y_max, z_height, E], feedrate)
    toolhead.move([x_min, y_min, z_height, E], feedrate)

    toolhead.dwell(0.5)
    accelerometer.stop_measurement('vibrations', append_time=True)
    accelerometer.wait_for_file_writes()

    # Re-enable input shaper if it was active
    if input_shaper is not None:
        input_shaper.enable_shaping()

    # Restore acceleration settings
    if old_mcr is not None:
        gcode.run_script_from_command(
            f'SET_VELOCITY_LIMIT ACCEL={old_accel} MINIMUM_CRUISE_RATIO={old_mcr} SQUARE_CORNER_VELOCITY={old_sqv}'
        )
    else:
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={old_accel} SQUARE_CORNER_VELOCITY={old_sqv}')

    toolhead.wait_moves()

    # Upload data and get results
    ConsoleOutput.print('Uploading data for processing...')
    try:
        with open(accelerometer.get_latest_data_file('vibrations'), 'rb') as f:
            response = requests.post(
                f'{webservice_url}/process/vibrations',
                files={'file': ('vibrations.csv', f)}
            )
            response.raise_for_status()
            
            # Save the returned graph
            with open('/tmp/vibrations_result.png', 'wb') as f:
                f.write(response.content)
            
            ConsoleOutput.print("Results saved to: /tmp/vibrations_result.png")
            
    except requests.exceptions.RequestException as e:
        raise gcmd.error(f"Failed to process data: {str(e)}")
    except IOError as e:
        raise gcmd.error(f"Failed to save results: {str(e)}")

    ConsoleOutput.print("Vibrations profile creation complete!")
