#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2011, 2012, 2013, 2014, 2015.

# Author(s):

#
#   Adam Dybbroe <adam.dybbroe@smhi.se>
#   Kristian Rune Larsen <krl@dmi.dk>
#   Lars Ørum Rasmussen <ras@dmi.dk>
#   Martin Raspaud <martin.raspaud@smhi.se>
#   David Hoese <david.hoese@ssec.wisc.edu>
#

# This file is part of mpop.

# mpop is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.

# mpop is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with
# mpop.  If not, see <http://www.gnu.org/licenses/>.

"""Interface to VIIRS SDR format

Format documentation:
http://npp.gsfc.nasa.gov/science/sciencedocuments/082012/474-00001-03_CDFCBVolIII_RevC.pdf

"""
import os.path
from datetime import datetime, timedelta
from trollsift.parser import globify
import numpy as np
import h5py
import logging
from collections import namedtuple

from mpop.projectable import Projectable
from mpop.readers import Reader
from fnmatch import fnmatch
import six

NO_DATE = datetime(1958, 1, 1)
EPSILON_TIME = timedelta(days=2)
LOG = logging.getLogger(__name__)


def _get_invalid_info(granule_data):
    """Get a detailed report of the missing data.
        N/A: not applicable
        MISS: required value missing at time of processing
        OBPT: onboard pixel trim (overlapping/bow-tie pixel removed during
            SDR processing)
        OGPT: on-ground pixel trim (overlapping/bow-tie pixel removed
            during EDR processing)
        ERR: error occurred during processing / non-convergence
        ELINT: ellipsoid intersect failed / instrument line-of-sight does
            not intersect the Earth’s surface
        VDNE: value does not exist / processing algorithm did not execute
        SOUB: scaled out-of-bounds / solution not within allowed range
    """
    if issubclass(granule_data.dtype.type, np.integer):
        msg = ("na:" + str((granule_data == 65535).sum()) +
               " miss:" + str((granule_data == 65534).sum()) +
               " obpt:" + str((granule_data == 65533).sum()) +
               " ogpt:" + str((granule_data == 65532).sum()) +
               " err:" + str((granule_data == 65531).sum()) +
               " elint:" + str((granule_data == 65530).sum()) +
               " vdne:" + str((granule_data == 65529).sum()) +
               " soub:" + str((granule_data == 65528).sum()))
    elif issubclass(granule_data.dtype.type, np.floating):
        msg = ("na:" + str((granule_data == -999.9).sum()) +
               " miss:" + str((granule_data == -999.8).sum()) +
               " obpt:" + str((granule_data == -999.7).sum()) +
               " ogpt:" + str((granule_data == -999.6).sum()) +
               " err:" + str((granule_data == -999.5).sum()) +
               " elint:" + str((granule_data == -999.4).sum()) +
               " vdne:" + str((granule_data == -999.3).sum()) +
               " soub:" + str((granule_data == -999.2).sum()))
    return msg


class FileKey(namedtuple("FileKey", ["name", "variable_name", "scaling_factors", "dtype", "standard_name", "units", "file_units", "kwargs"])):
    def __new__(cls, name, variable_name,
                scaling_factors=None, dtype=np.float32, standard_name=None, units=None, file_units=None, **kwargs):
        if isinstance(dtype, (str, six.text_type)):
            # get the data type from numpy
            dtype = getattr(np, dtype)
        return super(FileKey, cls).__new__(cls, name, variable_name, scaling_factors, dtype, standard_name, units, file_units, kwargs)


class HDF5MetaData(object):
    """Small class for inspecting a HDF5 file and retrieve its metadata/header data.
    """
    def __init__(self, filename, **kwargs):
        self.metadata = {}
        self.filename = filename
        if not os.path.exists(filename):
            raise IOError("File %s does not exist!" % filename)
        file_handle = h5py.File(self.filename, 'r')
        file_handle.visititems(self.collect_metadata)
        self._collect_attrs('', file_handle.attrs)
        file_handle.close()

    def _collect_attrs(self, name, attrs):
        for key, value in six.iteritems(attrs):
            value = np.squeeze(value)
            if issubclass(value.dtype.type, str):
                self.metadata["%s/attr/%s" % (name, key)] = str(value)
            else:
                self.metadata["%s/attr/%s" % (name, key)] = value

    def collect_metadata(self, name, obj):
        if isinstance(obj, h5py.Dataset):
            self.metadata[name] = obj
            self.metadata[name + "/shape"] = obj.shape
        self._collect_attrs(name, obj.attrs)

    def __getitem__(self, key):
        val = self.metadata[key]
        if isinstance(val, h5py.Dataset):
            # these datasets are closed and inaccessible when the file is closed, need to reopen
            return h5py.File(self.filename, 'r')[key].value
        return val


class SDRFileReader(HDF5MetaData):
    """VIIRS HDF5 File Reader
    """
    def __init__(self, file_type, filename, file_keys, **kwargs):
        super(SDRFileReader, self).__init__(filename, **kwargs)
        self.file_type = file_type
        self.file_keys = file_keys
        self.file_info = kwargs

        self.start_time = self.get_begin_time()
        self.end_time = self.get_end_time()

    def __getitem__(self, item):
        if item.endswith("/shape") and item[:-6] in self.file_keys:
            item = self.file_keys[item[:-6]].variable_name.format(**self.file_info) + "/shape"
        elif item in self.file_keys:
            item = self.file_keys[item].variable_name.format(**self.file_info)

        return super(SDRFileReader, self).__getitem__(item)

    def _parse_npp_datetime(self, datestr, timestr):
        try:
            datetime_str = datestr + timestr
        except TypeError:
            datetime_str = str(datestr.astype(str)) + str(timestr.astype(str))
        time_val = datetime.strptime(datetime_str, '%Y%m%d%H%M%S.%fZ')
        if abs(time_val - NO_DATE) < EPSILON_TIME:
            # catch rare case when SDR files have incorrect date
            raise ValueError("Datetime invalid %s " % time_val)
        return time_val

    def get_ring_lonlats(self):
        return self["gring_longitude"], self["gring_latitude"]

    def get_begin_time(self):
        return self._parse_npp_datetime(self['beginning_date'], self['beginning_time'])

    def get_end_time(self):
        return self._parse_npp_datetime(self['ending_date'], self['ending_time'])

    def get_begin_orbit_number(self):
        return int(self['beginning_orbit_number'])

    def get_end_orbit_number(self):
        return int(self['ending_orbit_number'])

    def get_platform_name(self):
        return self['platform_short_name']

    def get_sensor_name(self):
        return self['instrument_short_name']

    def get_geofilename(self):
        return self['geo_file_reference']

    def get_file_units(self, item):
        # What units should we expect from the file
        file_units = self.file_keys[item].file_units

        # Guess the file units if we need to (normally we would get this from the file)
        if file_units is None:
            if "radiance" in item:
                # we are getting some sort of radiance, probably DNB
                file_units = "W cm-2 sr-1"
            elif "reflectance" in item:
                # CF compliant unit for dimensionless
                file_units = "1"
            elif "temperature" in item:
                file_units = "K"
            elif "longitude" in item or "latitude" in item:
                file_units = "degrees"
            else:
                LOG.debug("Unknown units for file key '%s'", item)

        return file_units

    def get_units(self, item):
        units = self.file_keys[item].units
        file_units = self.get_file_units(item)
        # What units does the user want
        if units is None:
            # if the units in the file information
            return file_units
        return units

        # if calibrate == 2 and band not in VIIRS_DNB_BANDS:
        #     return "W m-2 um-1 sr-1"
        #
        # if band in VIIRS_IR_BANDS:
        #     return "K"
        # elif band in VIIRS_VIS_BANDS:
        #     return '%'
        # elif band in VIIRS_DNB_BANDS:
        #     return 'W m-2 sr-1'
        #
        # return None

    def scale_swath_data(self, data, mask, scaling_factors):
        """Scale swath data using scaling factors and offsets.

        Multi-granule (a.k.a. aggregated) files will have more than the usual two values.
        """
        num_grans = len(scaling_factors)/2
        gran_size = data.shape[0]/num_grans
        for i in range(num_grans):
            start_idx = i * gran_size
            end_idx = start_idx + gran_size
            m = scaling_factors[i*2]
            b = scaling_factors[i*2 + 1]
            # in rare cases the scaling factors are actually fill values
            if m <= -999 or b <= -999:
                mask[start_idx:end_idx] = 1
            else:
                data[start_idx:end_idx] *= m
                data[start_idx:end_idx] += b

    def adjust_scaling_factors(self, factors, file_units, output_units):
        if file_units == output_units:
            LOG.debug("File units and output units are the same (%s)", file_units)
            return factors
        if factors is None:
            factors = [1., 0.]
        factors = np.array(factors)

        if file_units == "W cm-2 sr-1" and output_units == "W m-2 sr-1":
            LOG.debug("Adjusting scaling factors to convert '%s' to '%s'", file_units, output_units)
            factors[::2] = np.where(factors[::2] != -999, factors[::2] * 10000.0, -999)
            factors[1::2] = np.where(factors[1::2] != -999, factors[1::2] * 10000.0, -999)
            return factors
        elif file_units == "1" and output_units == "%":
            LOG.debug("Adjusting scaling factors to convert '%s' to '%s'", file_units, output_units)
            factors[::2] = np.where(factors[::2] != -999, factors[::2] * 100.0, -999)
            factors[1::2] = np.where(factors[1::2] != -999, factors[1::2] * 100.0, -999)
            return factors
        else:
            return factors

    def get_swath_data(self, item, data_out=None, mask_out=None):
        """Get swath data, apply proper scalings, and apply proper masks.
        """
        # Can't guarantee proper file info until we get the data first
        var_info = self.file_keys[item]
        data = self[item]
        is_floating = np.issubdtype(data.dtype, np.floating)
        if data_out is not None:
            # This assumes that we are promoting the dtypes (ex. float file data -> int array)
            # and that it happens automatically when assigning to the existing out array
            data_out[:] = data
        else:
            data_out = data[:].astype(var_info.dtype)
            mask_out = np.zeros_like(data_out, dtype=np.bool)

        if var_info.scaling_factors:
            try:
                factors = self[var_info.scaling_factors]
            except KeyError:
                LOG.debug("No scaling factors found for %s", item)
                factors = None
        else:
            factors = None

        if is_floating:
            # If the data is a float then we mask everything <= -999.0
            fill_max = float(var_info.kwargs.get("fill_max_float", -999.0))
            mask_out[:] |= data_out <= fill_max
        else:
            # If the data is an integer then we mask everything >= fill_min_int
            fill_min = int(var_info.kwargs.get("fill_min_int", 65528))
            mask_out[:] |= data_out >= fill_min

        # Check if we need to do some unit conversion
        file_units = self.get_file_units(item)
        output_units = getattr(var_info, "units", file_units)
        factors = self.adjust_scaling_factors(factors, file_units, output_units)

        if factors is not None:
            self.scale_swath_data(data_out, mask_out, factors)

        return data_out, mask_out


class MultiFileReader(object):
    # FIXME: file_type isn't used here. Do we really need it ?
    def __init__(self, file_type, file_readers, file_keys, **kwargs):
        """
        :param file_type:
        :param file_readers: is a list of the reader instances to use.
        :param file_keys:
        :param kwargs:
        :return:
        """
        self.file_type = file_type
        self.file_readers = file_readers
        self.file_keys = file_keys

    @property
    def filenames(self):
        return [fr.filename for fr in self.file_readers]

    @property
    def start_time(self):
        return self.file_readers[0].start_time

    @property
    def end_time(self):
        return self.file_readers[-1].end_time

    def get_begin_orbit_number(self):
        return self.file_readers[0].get_begin_orbit_number()

    def get_end_orbit_number(self):
        return self.file_readers[-1].get_end_orbit_number()

    def get_platform_name(self):
        return self.file_readers[0].get_platform_name()

    def get_sensor_name(self):
        return self.file_readers[0].get_sensor_name()

    @property
    def geo_filenames(self):
        return [fr.get_geofilename() for fr in self.file_readers]

    def get_units(self, item):
        return self.file_readers[0].get_units(item)

    def get_swath_data(self, item, extra_mask=None, filename=None):
        var_info = self.file_keys[item]
        granule_shapes = [x[item + "/shape"] for x in self.file_readers]
        num_rows = sum([x[0] for x in granule_shapes])
        num_cols = granule_shapes[0][1]

        if filename:
            raise NotImplementedError("Saving data arrays to disk is not supported yet")
            # data = np.memmap(filename, dtype=var_info.dtype, mode='w', shape=(num_rows, num_cols))
        else:
            data = np.empty((num_rows, num_cols), dtype=var_info.dtype)
            if extra_mask is not None:
                mask = extra_mask.copy()
            else:
                mask = np.zeros_like(data, dtype=np.bool)

        idx = 0
        for granule_shape, file_reader in zip(granule_shapes, self.file_readers):
            # Get the data from each individual file reader (assumes it gets the data with the right data type)
            file_reader.get_swath_data(item,
                                       data_out=data[idx: idx + granule_shape[0]],
                                       mask_out=mask[idx: idx + granule_shape[0]])
            idx += granule_shape[0]

        # FIXME: This may get ugly when using memmaps, maybe move projectable creation here instead
        return np.ma.array(data, mask=mask, copy=False)


class VIIRSSDRReader(Reader):
    def __init__(self, **kwargs):
        self.file_types = {}
        self.file_readers = {}
        self.file_keys = {}
        self.navigations = {}
        self.calibrations = {}
        kwargs.setdefault("default_config_filename", "readers/viirs_sdr.cfg")

        # Load the configuration file and other defaults
        super(VIIRSSDRReader, self).__init__(**kwargs)

        # Determine what we know about the files provided and create file readers to read them
        file_types = self.identify_file_types(self.filenames)
        # TODO: Add ability to discover files when none are provided
        if not file_types:
            raise ValueError("No input files found matching the configured file types")

        num_files = 0
        for file_type_name, file_type_files in file_types.items():
            file_type_files = self._get_swathsegment(file_type_files)
            LOG.debug("File type %s has %d files after segment selection", file_type_name, len(file_type_files))

            if len(file_type_files) == 0:
                raise IOError("No VIIRS SDR files matching!: " +
                              "Start time = " + str(self.start_time) +
                              "  End time = " + str(self.end_time))
            elif num_files and len(file_type_files) != num_files:
                raise IOError("Varying numbers of files found", file_type_name)
            else:
                num_files = len(file_type_files)

            file_reader = MultiFileReader(file_type_name, file_types[file_type_name], self.file_keys)
            self.file_readers[file_type_name] = file_reader

    def _get_swathsegment(self, file_readers):
        if self.area is not None:
            from trollsched.spherical import SphPolygon
            from trollsched.boundary import AreaBoundary

            lons, lats = self.area.get_boundary_lonlats()
            area_boundary = AreaBoundary((lons.side1, lats.side1),
                                         (lons.side2, lats.side2),
                                         (lons.side3, lats.side3),
                                         (lons.side4, lats.side4))
            area_boundary.decimate(500)
            contour_poly = area_boundary.contour_poly

        segment_readers = []
        for file_reader in file_readers:
            file_start = file_reader.start_time
            file_end = file_reader.end_time

            # Search for multiple granules using an area
            if self.area is not None:
                coords = np.vstack(file_reader.get_ring_lonlats())
                poly = SphPolygon(np.deg2rad(coords))
                if poly.intersection(contour_poly) is not None:
                    segment_readers.append(file_reader)
                continue

            if self.start_time is None:
                # if no start_time, assume no time filtering
                segment_readers.append(file_reader)
                continue

            # Search for single granule using time start
            if self.end_time is None:
                if file_start <= self.start_time <= file_end:
                    segment_readers.append(file_reader)
                    continue
            else:
                # search for multiple granules
                # check that granule start time is inside interval
                if self.start_time <= file_start <= self.end_time:
                    segment_readers.append(file_reader)
                    continue

                # check that granule end time is inside interval
                if self.start_time <= file_end <= self.end_time:
                    segment_readers.append(file_reader)
                    continue

        return sorted(segment_readers, key=lambda x: x.start_time)

    def load_section_file_type(self, section_name, section_options):
        name = section_name.split(":")[-1]
        section_options["file_patterns"] = section_options["file_patterns"].split(",")
        # Don't create the file reader object yet
        self.file_types[name] = section_options

    def load_section_file_key(self, section_name, section_options):
        name = section_name.split(":")[-1]
        self.file_keys[name] = FileKey(name=name, **section_options)

    def load_section_navigation(self, section_name, section_options):
        name = section_name.split(":")[-1]
        self.navigations[name] = section_options

    def load_section_calibration(self, section_name, section_options):
        name = section_name.split(":")[-1]
        self.calibrations[name] = section_options

    def identify_file_types(self, filenames, default_file_reader="mpop.readers.viirs_sdr.SDRFileReader"):
        """Identify the type of a file by its filename or by its contents.

        Uses previously loaded information from the configuration file.
        """
        file_types = {}
        # remaining_filenames = [os.path.basename(fn) for fn in filenames]
        remaining_filenames = filenames[:]
        for file_type_name, file_type_info in self.file_types.items():
            file_types[file_type_name] = []
            file_reader_class = self._runtime_import(file_type_info.get("file_reader", default_file_reader))
            for file_pattern in file_type_info["file_patterns"]:
                tmp_remaining = []
                tmp_matching = []
                for fn in remaining_filenames:
                    # Add a wildcard to the front for path information
                    # FIXME: Is there a better way to generalize this besides removing the path every time
                    if fnmatch(fn, "*" + globify(file_pattern)):
                        reader = file_reader_class(file_type_name, fn, self.file_keys, **file_type_info)
                        tmp_matching.append(reader)
                    else:
                        tmp_remaining.append(fn)

                file_types[file_type_name].extend(tmp_matching)
                remaining_filenames = tmp_remaining

            if not file_types[file_type_name]:
                del file_types[file_type_name]

            if not remaining_filenames:
                break

        for remaining_filename in remaining_filenames:
            LOG.warning("Unidentified file: %s", remaining_filename)

        return file_types

    def _load_navigation(self, nav_name, dep_file_type, extra_mask=None):
        """Load the `nav_name` navigation.

        For VIIRS, if we haven't loaded the geolocation file read the `dep_file_type` header
        to figure out where it is.
        """
        nav_info = self.navigations[nav_name]
        lon_key = nav_info["longitude_key"]
        lat_key = nav_info["latitude_key"]
        file_type = nav_info["file_type"]

        if file_type in self.file_readers:
            file_reader = self.file_readers[file_type]
        else:
            LOG.debug("Geolocation files were not provided, will search band file header...")
            dataset_file_reader = self.file_readers[dep_file_type]
            base_dirs = [os.path.dirname(fn) for fn in dataset_file_reader.filenames]
            geo_filenames = dataset_file_reader.geo_filenames
            geo_filepaths = [os.path.join(bd, gf) for bd, gf in zip(base_dirs, geo_filenames)]

            file_types = self.identify_file_types(geo_filepaths)
            if file_type not in file_types:
                raise RuntimeError("The geolocation files from the header (ex. %s)"
                                   " do not match the configured geolocation (%s)" % (geo_filepaths[0], file_type))
            file_reader = MultiFileReader(file_type, file_types[file_type], self.file_keys)

        lon_data = file_reader.get_swath_data(lon_key, extra_mask=extra_mask)
        lat_data = file_reader.get_swath_data(lat_key, extra_mask=extra_mask)

        # FIXME: Is this really needed/does it belong here? Can we have a dummy/simple object?
        from pyresample import geometry
        area = geometry.SwathDefinition(lons=lon_data, lats=lat_data)
        area_name = ("swath_" +
                     file_reader.start_time.isoformat() + "_" +
                     file_reader.end_time.isoformat() + "_" +
                     str(lon_data.shape[0]) + "_" + str(lon_data.shape[1]))
        # FIXME: Which one is used now:
        area.area_id = area_name
        area.name = area_name

        return area

    def _get_dataset_info(self, name, calibration):
        dataset_info = self.datasets[name].copy()

        if not dataset_info.get("calibration", None):
            LOG.debug("No calibration set for '%s'", name)
            dataset_info["file_type"] = dataset_info["file_type"][0]
            dataset_info["file_key"] = dataset_info["file_key"][0]
            dataset_info["navigation"] = dataset_info["navigation"][0]
            return dataset_info

        # Remove any file types and associated calibration, file_key, navigation if file_type is not loaded
        for k in ["file_type", "file_key", "calibration", "navigation"]:
            dataset_info[k] = []
        for idx, ft in enumerate(self.datasets[name]["file_type"]):
            if ft in self.file_readers:
                for k in ["file_type", "file_key", "calibration", "navigation"]:
                    dataset_info[k].append(self.datasets[name][k][idx])

        # By default do the first calibration for a dataset
        cal_index = 0
        cal_name = dataset_info["calibration"][0]
        for idx, cname in enumerate(dataset_info["calibration"]):
            # is this the calibration we want for this channel?
            if cname in calibration:
                cal_index = idx
                cal_name = cname
                LOG.debug("Using calibration '%s' for dataset '%s'", cal_name, name)
                break
        else:
            LOG.debug("Using default calibration '%s' for dataset '%s'", cal_name, name)

        # Load metadata and calibration information for this dataset
        try:
            cal_info = self.calibrations.get(cal_name, None)
            for k, info_dict in [
                ("file_type", self.file_types),
                ("file_key", self.file_keys),
                ("navigation", self.navigations),
                ("calibration", self.calibrations)]:
                val = dataset_info[k][cal_index]
                if cal_info is not None:
                    val = cal_info.get(k, val)

                if val not in info_dict and k != "calibration":
                    # We don't care if the calibration has its own section
                    raise RuntimeError("Unknown '%s': %s" % (k, val,))
                dataset_info[k] = val

                if k == "file_key":
                    # collect any other metadata
                    dataset_info["standard_name"] = self.file_keys[val].standard_name
                    # dataset_info["file_units"] = self.file_keys[val].file_units
                    # dataset_info["units"] = self.file_keys[val].units
        except (IndexError, KeyError):
            raise RuntimeError("Could not get information to perform calibration '%s'" % (cal_name,))

        return dataset_info

    def load(self, datasets_to_load, calibration=None, **dataset_info):
        if dataset_info:
            LOG.warning("Unsupported options for viirs reader: %s", str(dataset_info))
        if calibration is None:
            calibration = getattr(self, "calibration", ["bt", "reflectance"])
        # order calibration from highest level to lowest level
        calibration = [x for x in ["bt", "reflectance", "radiance", "counts"] if x in calibration]

        datasets_to_load = set(datasets_to_load) & set(self.dataset_names)
        if len(datasets_to_load) == 0:
            LOG.debug("No datasets to load from this reader")
            # XXX: Is None really the best thing that can be returned here?
            return

        LOG.debug("Channels to load: " + str(datasets_to_load))

        # Sanity check and get the navigation sets being used
        areas = {}
        datasets_loaded = {}
        for ds in datasets_to_load:
            dataset_info = self._get_dataset_info(ds, calibration=calibration)
            file_type = dataset_info["file_type"]
            file_key = dataset_info["file_key"]
            file_reader = self.file_readers[file_type]
            nav_name = dataset_info["navigation"]

            # Get the swath data (fully scaled and in the correct data type)
            data = file_reader.get_swath_data(file_key)

            # Load the navigation information first
            if nav_name not in areas:
                # FIXME: This ignores the possibility that data masks are different between bands
                areas[nav_name] = area = self._load_navigation(nav_name, file_type, extra_mask=data.mask)
            else:
                area = areas[nav_name]

            # Create a projectable from info from the file data and the config file
            # FIXME: Remove metadata that is reader only
            dataset_info.setdefault("units", file_reader.get_units(file_key))
            dataset_info.setdefault("platform", file_reader.get_platform_name())
            dataset_info.setdefault("sensor", file_reader.get_sensor_name())
            dataset_info.setdefault("start_orbit", file_reader.get_begin_orbit_number())
            dataset_info.setdefault("end_orbit", file_reader.get_end_orbit_number())
            dataset_info.setdefault("rows_per_scan", self.navigations[nav_name]["rows_per_scan"])
            projectable = Projectable(data=data,
                                      start_time=file_reader.start_time,
                                      end_time=file_reader.end_time,
                                      **dataset_info)
            projectable.info["area"] = area

            datasets_loaded[ds] = projectable
        return datasets_loaded
