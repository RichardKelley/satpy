#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author(s):
#
#   Panu Lahtinen <panu.lahtinen@fmi.fi
#
# This file is part of mpop.
#
# mpop is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# mpop is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# mpop.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import mpop.satin
try:
    from unittest import mock
except ImportError:
    import mock

'''Integration testing of
 - :mod:`mpop.satin`
'''


class TestReaders(unittest.TestCase):

    '''Class for testing mpop.satin'''

    # def test_lonlat_to_geo_extent(self):
    #     '''Test conversion of longitudes and latitudes to area extent.'''
    #
    #     # MSG3 proj4 string from
    #     #  xrit.sat.load(..., only_metadata=True).proj4_params
    #     proj4_str = 'proj=geos lon_0=0.00 lat_0=0.00 ' \
    #         'a=6378169.00 b=6356583.80 h=35785831.00'
    #
    #     # MSG3 maximum extent
    #     max_extent=(-5567248.07, -5570248.48,
    #                  5570248.48, 5567248.07)
    #
    #     # Few area extents in longitudes/latitudes
    #     area_extents_ll = [[-68.328121068060341, # left longitude
    #                          18.363816196771392, # down latitude
    #                          74.770372053870972, # right longitude
    #                          75.66494585661934], # up latitude
    #                        # all corners outside Earth's disc
    #                        [1e30, 1e30, 1e30, 1e30]
    #                        ]
    #
    #     # And corresponding correct values in GEO projection
    #     geo_extents = [[-5010596.02, 1741593.72, 5570248.48, 5567248.07],
    #                    [-5567248.07, -5570248.48, 5570248.48, 5567248.07]]
    #
    #     for i in range(len(area_extents_ll)):
    #         res = mpop.satin.mipp_xrit.lonlat_to_geo_extent(area_extents_ll[i],
    #                                                         proj4_str,
    #                                                         max_extent=\
    #                                                             max_extent)
    #         for j in range(len(res)):
    #             self.assertAlmostEqual(res[j], geo_extents[i][j], 2)

    def test_get_filenames_with_start_time_provided(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 0)}

        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57),  # file1
                                                               "end_time": datetime(2015, 6, 23, 23, 59)},
                                                              {"start_time": datetime(2015, 6, 23, 23, 59),  # file2
                                                               "end_time": datetime(2015, 6, 24, 0, 1)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 1),    # file3
                                                               "end_time": datetime(2015, 6, 24, 0, 3)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 3),    # file4
                                                               "end_time": datetime(2015, 6, 24, 0, 5)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 5),    # file5
                                                               "end_time": datetime(2015, 6, 24, 0, 7)},
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), ["file2"])

    @mock.patch("glob.glob")
    def test_find_sensors_readers_single_sensor_no_files(self, glob_mock, **mock_objs):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        glob_mock.return_value = ["valid", "no_found_files", "not_valid"]

        def fake_read_config(config_file):
            if config_file in ["valid", "no_found_files"]:
                return {"name": "fake_reader",
                        "sensor": ["foo"],
                        "config_file": config_file}
            else:
                raise ValueError("Fake ValueError")

        def fake_get_filenames(reader_info):
            if reader_info["config_file"] == "valid":
                return ["file1", "file2"]
            return []

        with mock.patch.multiple("mpop.readers.ReaderFinder",
                                 _read_reader_config=mock.DEFAULT,
                                 get_filenames=mock.DEFAULT,
                                 _load_reader=mock.DEFAULT) as mock_objs:
            mock_objs["_read_reader_config"].side_effect = fake_read_config
            mock_objs["get_filenames"].side_effect = fake_get_filenames

            scn = Scene()
            finder = ReaderFinder(scn)
            finder._find_sensors_readers("foo", None)

    def test_get_filenames_with_start_time_and_end_time(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 0),
                       "end_time": datetime(2015, 6, 24, 0, 6)}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57),  # file1
                                                               "end_time": datetime(2015, 6, 23, 23, 59)},
                                                              {"start_time": datetime(2015, 6, 23, 23, 59),  # file2
                                                               "end_time": datetime(2015, 6, 24, 0, 1)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 1),    # file3
                                                               "end_time": datetime(2015, 6, 24, 0, 3)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 3),    # file4
                                                               "end_time": datetime(2015, 6, 24, 0, 5)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 5),    # file5
                                                               "end_time": datetime(2015, 6, 24, 0, 7)},
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), ["file2", "file3", "file4", "file5"])

    def test_get_filenames_with_start_time_and_npp_style_end_time(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 0),
                       "end_time": datetime(2015, 6, 24, 0, 6)}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57),  # file1
                                                               "end_time": datetime(1950, 1, 1, 23, 59)},
                                                              {"start_time": datetime(2015, 6, 23, 23, 59),  # file2
                                                               "end_time": datetime(1950, 1, 1, 0, 1)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 1),    # file3
                                                               "end_time": datetime(1950, 1, 1, 0, 3)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 3),    # file4
                                                               "end_time": datetime(1950, 1, 1, 0, 5)},
                                                              {"start_time": datetime(2015, 6, 24, 0, 5),    # file5
                                                               "end_time": datetime(1950, 1, 1, 0, 7)},
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), ["file2", "file3", "file4", "file5"])

    def test_get_filenames_with_start_time(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 0),
                       "end_time": datetime(2015, 6, 24, 0, 6)}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57)},  # file1
                                                              {"start_time": datetime(2015, 6, 23, 23, 59)},  # file2
                                                              {"start_time": datetime(2015, 6, 24, 0, 1)},    # file3
                                                              {"start_time": datetime(2015, 6, 24, 0, 3)},    # file4
                                                              {"start_time": datetime(2015, 6, 24, 0, 5)},    # file5
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), ["file3", "file4", "file5"])

    def test_get_filenames_with_only_start_times_wrong(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 0)}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57)},  # file1
                                                              {"start_time": datetime(2015, 6, 23, 23, 59)},  # file2
                                                              {"start_time": datetime(2015, 6, 24, 0, 1)},    # file3
                                                              {"start_time": datetime(2015, 6, 24, 0, 3)},    # file4
                                                              {"start_time": datetime(2015, 6, 24, 0, 5)},    # file5
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), [])

    def test_get_filenames_with_only_start_times_right(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene()
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": datetime(2015, 6, 24, 0, 1)}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57)},  # file1
                                                              {"start_time": datetime(2015, 6, 23, 23, 59)},  # file2
                                                              {"start_time": datetime(2015, 6, 24, 0, 1)},    # file3
                                                              {"start_time": datetime(2015, 6, 24, 0, 3)},    # file4
                                                              {"start_time": datetime(2015, 6, 24, 0, 5)},    # file5
                                                              ]
                self.assertEqual(finder.get_filenames(reader_info), ["file3"])

    def test_get_filenames_to_error(self):
        from mpop.scene import Scene
        from mpop.readers import ReaderFinder
        from datetime import datetime
        scn = Scene(start_time="bla")
        finder = ReaderFinder(scn)
        reader_info = {"file_patterns": ["foo"],
                       "start_time": None}
        with mock.patch("mpop.readers.glob.iglob") as mock_iglob:
            mock_iglob.return_value = ["file1", "file2", "file3", "file4", "file5"]
            with mock.patch("mpop.readers.Parser") as mock_parser:
                mock_parser.return_value.parse.side_effect = [{"start_time": datetime(2015, 6, 23, 23, 57)},  # file1
                                                              {"start_time": datetime(2015, 6, 23, 23, 59)},  # file2
                                                              {"start_time": datetime(2015, 6, 24, 0, 1)},    # file3
                                                              {"start_time": datetime(2015, 6, 24, 0, 3)},    # file4
                                                              {"start_time": datetime(2015, 6, 24, 0, 5)},    # file5
                                                              ]
                self.assertRaises(ValueError, finder.get_filenames, reader_info)


def suite():
    """The test suite for test_scene.
    """
    loader = unittest.TestLoader()
    mysuite = unittest.TestSuite()
    mysuite.addTest(loader.loadTestsFromTestCase(TestReaders))

    return mysuite

if __name__ == "__main__":
    unittest.main()
