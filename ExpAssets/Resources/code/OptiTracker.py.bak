import os
import numpy as np
from scipy.signal import butter, lfilter, freqz, sosfiltfilt

# TODO:
#  - grab first frame, row count indicates num markers tracked.
#  - incorporate checks to ensure frames queried match expected marker count
#  - refactor nomeclature about frame indexing/querying


class OptiTracker(object):
    """
    A class for querying and operating on motion tracking data.

    This class processes positional data from markers, providing functionality
    to calculate velocities and positions in 3D space. It handles data loading,
    frame querying, and various spatial calculations.

    Attributes:
        marker_count (int): Number of markers to track
        sample_rate (int): Sampling rate of the tracking system in Hz
        window_size (int): Number of frames to consider for calculations
        data_dir (str): Directory path containing the tracking data files

    Methods:
        velocity(num_frames): Calculate velocity based on marker positions across specified number of frames
        position(): Get current position of markers
        distance(num_frames: int): Calculate distance traveled over specified number of frames
    """

    def __init__(
        self,
        marker_count: int,
        sample_rate: int = 120,
        window_size: int = 5,
        data_dir: str = "",
    ):
        """
        Initialize the OptiTracker object.

        Args:
            marker_count (int): Number of markers to track
            sample_rate (int, optional): Sampling rate in Hz. Defaults to 120.
            window_size (int, optional): Number of frames for calculations. Defaults to 5.
            data_dir (str, optional): Path to data directory. Defaults to empty string.
        """

        if marker_count:
            self.__marker_count = marker_count

        self._sample_rate = sample_rate
        self._data_dir = data_dir
        self._window_size = window_size

    @property
    def marker_count(self) -> int:
        """Get the number of markers to track."""
        return self.__marker_count

    @marker_count.setter
    def marker_count(self, marker_count: int) -> None:
        """Set the number of markers to track."""
        self.__marker_count = marker_count

    @property
    def data_dir(self) -> str:
        """Get the data directory path."""
        return self._data_dir

    @data_dir.setter
    def data_dir(self, data_dir: str) -> None:
        """Set the data directory path."""
        self._data_dir = data_dir

    @property
    def sample_rate(self) -> int:
        """Get the sampling rate."""
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, sample_rate: int) -> None:
        """Set the sampling rate."""
        self._sample_rate = sample_rate

    @property
    def window_size(self) -> int:
        """Get the window size."""
        return self._window_size

    @window_size.setter
    def window_size(self, window_size: int) -> None:
        """Set the window size."""
        self._window_size = window_size

    def velocity(self, num_frames: int = 0) -> float:
        """Calculate and return the current velocity."""
        if num_frames == 0:
            num_frames = self._window_size

        if num_frames < 2:
            raise ValueError("Window size must cover at least two frames.")

        frames = self.__query_frames(num_frames)
        return self.__velocity(frames)

    def position(self) -> np.ndarray:
        """Get the current position of markers."""
        frame = self.__query_frames(num_frames=1)
        return self.__column_means(frame)

    def distance(self, num_frames: int = 0) -> float:
        """Calculate and return the distance traveled over the specified number of frames."""

        if num_frames == 0:
            num_frames = self._window_size

        frames = self.__query_frames(num_frames)
        return self.__euclidean_distance(frames)

    def __velocity(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate velocity using position data over the specified window.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            float: Calculated velocity in cm/s
        """
        if self._window_size < 2:
            raise ValueError("Window size must cover at least two frames.")

        if len(frames) == 0:
            frames = self.__query_frames()

        euclidean_distance = self.__euclidean_distance(frames)

        return euclidean_distance / (frames.shape[0] / self._sample_rate)

    def __euclidean_distance(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate Euclidean distance between first and last frames.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            float: Euclidean distance
        """

        if frames.size == 0:
            frames = self.__query_frames()

        positions = self.__column_means(frames)

        return float(
            np.sqrt(
                (positions["pos_x"][-1] - positions["pos_x"][0]) ** 2
                + (positions["pos_y"][-1] - positions["pos_y"][0]) ** 2
                + (positions["pos_z"][-1] - positions["pos_z"][0]) ** 2
            )
        )

    # TODO: reduce dependencies by hand-rolling a butterworth filter
    # TODO: but first make sure this isn't a bad idea.

    def __smooth(self, order=2, cutoff=10, filtype="low", frames: np.ndarray = np.array([])) -> np.ndarray:
        """
        Apply a Butterworth filter to the position data.

        Args:
            order (int, optional): Order of the Butterworth filter. Defaults to 2.
            cutoff (int, optional): Cutoff frequency in Hz. Defaults to 10.
            filtype (str, optional): Type of filter to apply. Defaults to "low".
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            np.ndarray: Array of filtered positions
        """
        if len(frames) == 0:
            frames = self.__query_frames()

        # Create output array with the correct dtype
        smooth = np.zeros(
            len(frames),
            dtype=[
                ("frame_number", "i8"),
                ("pos_x", "f8"),
                ("pos_y", "f8"),
                ("pos_z", "f8"),
            ],
        )


        butt = butter(N=order, Wn=cutoff, btype=filtype, output="sos", fs=self._sample_rate)

        smooth["pos_x"] = sosfiltfilt(sos=butt, x=frames["pos_x"], padlen=None)
        smooth["pos_y"] = sosfiltfilt(sos=butt, x=frames["pos_y"], padlen=None)
        smooth["pos_z"] = sosfiltfilt(sos=butt, x=frames["pos_z"], padlen=None)

        return smooth

    def __column_means(self, frames: np.ndarray = np.array([])) -> np.ndarray:
        """
        Calculate column means of position data.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            np.ndarray: Array of mean positions
        """
        if len(frames) == 0:
            frames = self.__query_frames()

        # Create output array with the correct dtype
        means = np.zeros(
            len(frames) // self.__marker_count,
            dtype=[
                ("frame_number", "i8"),
                ("pos_x", "f8"),
                ("pos_y", "f8"),
                ("pos_z", "f8"),
            ],
        )

        # Group by marker (every nth row where n is marker_count)
        for frame in range(1, len(frames) // self.__marker_count + 1):
            frame_data = frames[frame,]

            means[frame - 1]["pos_x"] = np.mean(frame_data["pos_x"])
            means[frame - 1]["pos_y"] = np.mean(frame_data["pos_y"])
            means[frame - 1]["pos_z"] = np.mean(frame_data["pos_z"])

        return means

    def __query_frames(self, num_frames: int = 0) -> np.ndarray:
        """
        Query and process frame data from the data file.

        Args:
            num_frames (int, optional): Number of frames to query. Defaults to window_size when empty.

        Returns:
            np.ndarray: Array of queried frame data

        Raises:
            ValueError: If data directory is not set or data format is invalid
            FileNotFoundError: If data directory does not exist
        """

        if self._data_dir == "":
            raise ValueError("No data directory was set.")

        if not os.path.exists(self._data_dir):
            raise FileNotFoundError(f"Data directory not found at:\n{self._data_dir}")

        if num_frames < 0:
            raise ValueError("Number of frames cannot be negative.")

        with open(self._data_dir, "r") as file:
            header = file.readline().strip().split(",")

        if any(col not in header for col in ["frame_number", "pos_x", "pos_y", "pos_z"]):
            raise ValueError(
                "Data file must contain columns named frame, pos_x, pos_y, pos_z."
            )

        dtype_map = [
            # coerce expected columns to float | int, default to string otherwise
            (
                name,
                (
                    "float"
                    if name in ["pos_x", "pos_y", "pos_z"]
                    else "int" if name == "frame_number" else "U32"
                ),
            )
            for name in header
        ]

        # read in data now that columns have been validated and typed
        data = np.genfromtxt(
            self._data_dir, delimiter=",", dtype=dtype_map, skip_header=1
        )

        if num_frames == 0:
            num_frames = self._window_size

        # Calculate which frames to include
        last_frame = data["frame_number"][-1]
        lookback = last_frame - num_frames

        # Filter for relevant frames
        data = data[data["frame_number"] > lookback]

        data = self.__smooth(frames=data)

        return data
