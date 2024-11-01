# Shake&Tune: 3D printer analysis tools
#
# Copyright (C) 2024 Félix Boisselier <felix@fboisselier.fr> (Frix_x on Discord)
# Licensed under the GNU General Public License v3.0 (GPL-3.0)

import requests
from ..helpers.common_func import AXIS_CONFIG
from ..helpers.console_output import ConsoleOutput
from ..helpers.resonance_test import vibrate_axis
from ..shaketune_process import ShakeTuneProcess
from .accelerometer import Accelerometer

def compare_belts_responses_web(gcmd, config, st_process: ShakeTuneProcess) -> None:
    # Get webservice URL parameter
    webservice_url = gcmd.get('URL', default='http://localhost:5000')
    webservice_url = webservice_url.rstrip('/')  # Remove trailing slash if present
    
    printer = config.get_printer()
    toolhead = printer.lookup_object('toolhead')
    res_tester = printer.lookup_object('resonance_tester')
    systime = printer.get_reactor().monotonic()

    # Get parameters with validation
    min_freq = gcmd.get_float('FREQ_START', default=res_tester.test.min_freq, minval=1)
    max_freq = gcmd.get_float('FREQ_END', default=res_tester.test.max_freq, minval=1)
    hz_per_sec = gcmd.get_float('HZ_PER_SEC', default=1, minval=1)
    accel_per_hz = gcmd.get_float('ACCEL_PER_HZ', default=None)
    feedrate_travel = gcmd.get_float('TRAVEL_SPEED', default=120.0, minval=20.0)
    z_height = gcmd.get_float('Z_HEIGHT', default=None, minval=1)

    if accel_per_hz == '':
        accel_per_hz = None

    if accel_per_hz is None:
        accel_per_hz = res_tester.test.accel_per_hz

    gcode = printer.lookup_object('gcode')
    max_accel = max_freq * accel_per_hz

    # Move to the starting point
    test_points = res_tester.test.get_start_test_points()
    if len(test_points) > 1:
        raise gcmd.error('Only one test point in the [resonance_tester] section is supported by Shake&Tune.')
    if test_points[0] == (-1, -1, -1):
        if z_height is None:
            raise gcmd.error(
                'Z_HEIGHT parameter is required if the test_point in [resonance_tester] section is set to -1,-1,-1'
            )
        kin_info = toolhead.kin.get_status(systime)
        mid_x = (kin_info['axis_minimum'].x + kin_info['axis_maximum'].x) / 2
        mid_y = (kin_info['axis_minimum'].y + kin_info['axis_maximum'].y) / 2
        point = (mid_x, mid_y, z_height)
    else:
        x, y, z = test_points[0]
        if z_height is not None:
            z = z_height
        point = (x, y, z)

    toolhead.manual_move(point, feedrate_travel)
    toolhead.dwell(0.5)

    # Save and update acceleration settings
    toolhead_info = toolhead.get_status(systime)
    old_accel = toolhead_info['max_accel']
    if 'minimum_cruise_ratio' in toolhead_info:
        old_mcr = toolhead_info['minimum_cruise_ratio']
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={max_accel} MINIMUM_CRUISE_RATIO=0')
    else:
        old_mcr = None
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={max_accel}')

    # Disable input shaper if active
    input_shaper = printer.lookup_object('input_shaper', None)
    if input_shaper is not None:
        input_shaper.disable_shaping()

    measurements = []
    
    # Test both belts
    for belt in ['a', 'b']:
        # Find accelerometer for belt
        accel_chip = Accelerometer.find_axis_accelerometer(printer, belt)
        if accel_chip is None:
            raise gcmd.error(f'No suitable accelerometer found for belt {belt.upper()}!')
        accelerometer = Accelerometer(printer.get_reactor(), printer.lookup_object(accel_chip))

        # Perform measurement
        accelerometer.start_measurement()
        vibrate_axis(toolhead, gcode, belt, min_freq, max_freq, hz_per_sec, accel_per_hz)
        accelerometer.stop_measurement(f'belt_{belt}', append_time=True)
        measurements.append((f'belt_{belt}', accelerometer.get_latest_data_file(f'belt_{belt}')))

        accelerometer.wait_for_file_writes()
        toolhead.dwell(1)
        toolhead.wait_moves()

    # Re-enable input shaper if it was active
    if input_shaper is not None:
        input_shaper.enable_shaping()

    # Restore acceleration settings
    if old_mcr is not None:
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={old_accel} MINIMUM_CRUISE_RATIO={old_mcr}')
    else:
        gcode.run_script_from_command(f'SET_VELOCITY_LIMIT ACCEL={old_accel}')

    # Upload data and get results
    ConsoleOutput.print('Uploading data for processing...')
    for test_name, filepath in measurements:
        try:
            with open(filepath, 'rb') as f:
                response = requests.post(
                    f'{webservice_url}/process/belts',
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

    ConsoleOutput.print("Belt response comparison complete!")
