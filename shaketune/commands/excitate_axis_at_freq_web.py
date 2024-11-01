#!/usr/bin/env python3

# Shake&Tune: 3D printer analysis tools
#
# Copyright (C) 2024 Félix Boisselier <felix@fboisselier.fr> (Frix_x on Discord)
# Licensed under the GNU General Public License v3.0 (GPL-3.0)

import requests
from ..helpers.common_func import AXIS_CONFIG
from ..helpers.console_output import ConsoleOutput
from ..helpers.resonance_test import vibrate_axis_at_static_freq
from ..shaketune_process import ShakeTuneProcess
from .accelerometer import Accelerometer

def excitate_axis_at_freq_web(gcmd, config, st_process: ShakeTuneProcess) -> None:
    # Get webservice URL parameter
    webservice_url = gcmd.get('URL', default='http://localhost:5000')
    webservice_url = webservice_url.rstrip('/')  # Remove trailing slash if present
    
    create_graph = gcmd.get_int('CREATE_GRAPH', default=0, minval=0, maxval=1) == 1
    freq = gcmd.get_int('FREQUENCY', default=25, minval=1)
    duration = gcmd.get_int('DURATION', default=30, minval=1)
    accel_per_hz = gcmd.get_float('ACCEL_PER_HZ', default=None)
    axis = gcmd.get('AXIS', default='x').lower()
    feedrate_travel = gcmd.get_float('TRAVEL_SPEED', default=120.0, minval=20.0)
    z_height = gcmd.get_float('Z_HEIGHT', default=None, minval=1)
    accel_chip = gcmd.get('ACCEL_CHIP', default=None)

    if accel_chip == '':
        accel_chip = None
    if accel_per_hz == '':
        accel_per_hz = None

    axis_config = next((item for item in AXIS_CONFIG if item['axis'] == axis), None)
    if axis_config is None:
        raise gcmd.error('AXIS selection invalid. Should be either x, y, a or b!')

    if create_graph:
        printer = config.get_printer()
        if accel_chip is None:
            accel_chip = Accelerometer.find_axis_accelerometer(printer, 'xy' if axis in {'a', 'b'} else axis)
        k_accelerometer = printer.lookup_object(accel_chip, None)
        if k_accelerometer is None:
            raise gcmd.error(f'Accelerometer chip [{accel_chip}] was not found!')
        accelerometer = Accelerometer(printer.get_reactor(), k_accelerometer)

    ConsoleOutput.print(f'Excitating {axis.upper()} axis at {freq}Hz for {duration} seconds')

    printer = config.get_printer()
    gcode = printer.lookup_object('gcode')
    toolhead = printer.lookup_object('toolhead')
    res_tester = printer.lookup_object('resonance_tester')
    systime = printer.get_reactor().monotonic()

    if accel_per_hz is None:
        accel_per_hz = res_tester.test.accel_per_hz

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

    # Disable input shaper if active
    input_shaper = printer.lookup_object('input_shaper', None)
    if input_shaper is not None:
        input_shaper.disable_shaping()
    else:
        input_shaper = None

    # If the user wants to create a graph, we start accelerometer recording
    if create_graph:
        accelerometer.start_measurement()

    toolhead.dwell(0.5)
    vibrate_axis_at_static_freq(toolhead, gcode, axis_config['direction'], freq, duration, accel_per_hz)
    toolhead.dwell(0.5)

    # Re-enable input shaper if it was active
    if input_shaper is not None:
        input_shaper.enable_shaping()

    # If the user wanted to create a graph, we stop the recording and process it
    if create_graph:
        accelerometer.stop_measurement('excitation', append_time=True)
        accelerometer.wait_for_file_writes()

        # Upload data and get results
        ConsoleOutput.print('Uploading data for processing...')
        try:
            with open(accelerometer.get_latest_data_file('excitation'), 'rb') as f:
                response = requests.post(
                    f'{webservice_url}/process/excitate',
                    files={'file': ('excitation.csv', f)}
                )
                response.raise_for_status()
                
                # Save the returned graph
                with open('/tmp/excitation_result.png', 'wb') as f:
                    f.write(response.content)
                
                ConsoleOutput.print("Results saved to: /tmp/excitation_result.png")
                
        except requests.exceptions.RequestException as e:
            raise gcmd.error(f"Failed to process data: {str(e)}")
        except IOError as e:
            raise gcmd.error(f"Failed to save results: {str(e)}")

        ConsoleOutput.print("Axis excitation test complete!")
