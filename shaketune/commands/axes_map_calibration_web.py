# Shake&Tune: 3D printer analysis tools
#
# Copyright (C) 2024 Félix Boisselier <felix@fboisselier.fr> (Frix_x on Discord)
# Licensed under the GNU General Public License v3.0 (GPL-3.0)

import requests
from ..helpers.console_output import ConsoleOutput
from ..shaketune_process import ShakeTuneProcess
from .accelerometer import Accelerometer

SEGMENT_LENGTH = 30  # mm

def axes_map_calibration_web(gcmd, config, st_process: ShakeTuneProcess) -> None:
    # Get webservice URL parameter
    webservice_url = gcmd.get('URL', default='http://localhost:5000')
    webservice_url = webservice_url.rstrip('/')  # Remove trailing slash if present
    
    # Get parameters with validation
    z_height = gcmd.get_float('Z_HEIGHT', default=20.0)
    speed = gcmd.get_float('SPEED', default=80.0, minval=20.0)
    accel = gcmd.get_int('ACCEL', default=1500, minval=100)
    feedrate_travel = gcmd.get_float('TRAVEL_SPEED', default=120.0, minval=20.0)

    printer = config.get_printer()
    gcode = printer.lookup_object('gcode')
    toolhead = printer.lookup_object('toolhead')
    systime = printer.get_reactor().monotonic()

    # Find and validate accelerometer
    accel_chip = Accelerometer.find_axis_accelerometer(printer, 'xy')
    k_accelerometer = printer.lookup_object(accel_chip, None)
    if k_accelerometer is None:
        raise gcmd.error('Multi-accelerometer configurations are not supported for this macro!')
    
    pconfig = printer.lookup_object('configfile')
    current_axes_map = pconfig.status_raw_config[accel_chip].get('axes_map', None)
    if current_axes_map is not None and current_axes_map.strip().replace(' ', '') != 'x,y,z':
        raise gcmd.error(
            f'The parameter axes_map is already set in your {accel_chip} configuration! Please remove it (or set it to "x,y,z")!'
        )
    
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
    mid_x = (kin_info['axis_minimum'].x + kin_info['axis_maximum'].x) / 2
    mid_y = (kin_info['axis_minimum'].y + kin_info['axis_maximum'].y) / 2
    _, _, _, E = toolhead.get_position()

    # Move to start position
    toolhead.move([mid_x - SEGMENT_LENGTH / 2, mid_y - SEGMENT_LENGTH / 2, z_height, E], feedrate_travel)
    toolhead.dwell(0.5)

    # Perform measurements for each axis
    measurements = []
    
    # X axis
    accelerometer.start_measurement()
    toolhead.dwell(0.5)
    toolhead.move([mid_x + SEGMENT_LENGTH / 2, mid_y - SEGMENT_LENGTH / 2, z_height, E], speed)
    toolhead.dwell(0.5)
    accelerometer.stop_measurement('axesmap_X', append_time=True)
    measurements.append(('axesmap_X', accelerometer.get_latest_data_file('axesmap_X')))
    toolhead.dwell(0.5)

    # Y axis
    accelerometer.start_measurement()
    toolhead.dwell(0.5)
    toolhead.move([mid_x + SEGMENT_LENGTH / 2, mid_y + SEGMENT_LENGTH / 2, z_height, E], speed)
    toolhead.dwell(0.5)
    accelerometer.stop_measurement('axesmap_Y', append_time=True)
    measurements.append(('axesmap_Y', accelerometer.get_latest_data_file('axesmap_Y')))
    toolhead.dwell(0.5)

    # Z axis
    accelerometer.start_measurement()
    toolhead.dwell(0.5)
    toolhead.move([mid_x + SEGMENT_LENGTH / 2, mid_y + SEGMENT_LENGTH / 2, z_height + SEGMENT_LENGTH, E], speed)
    toolhead.dwell(0.5)
    accelerometer.stop_measurement('axesmap_Z', append_time=True)
    measurements.append(('axesmap_Z', accelerometer.get_latest_data_file('axesmap_Z')))

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
    for test_name, filepath in measurements:
        try:
            with open(filepath, 'rb') as f:
                response = requests.post(
                    f'{webservice_url}/process/axes_map',
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

    ConsoleOutput.print("Axes map calibration complete!")
