import os
import numpy as np

# TODO:
#  - grab first frame, row count indicates num markers tracked.
#  - incorporate checks to ensure frames queried match expected marker count


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

        positions = self.__column_means(frames)

        euclidean_distance = self.__euclidean_distance(positions)

        velocity = euclidean_distance / (self._window_size / self._sample_rate)

        return float(velocity)

    def __euclidean_distance(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate Euclidean distance between first and last frames.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            float: Euclidean distance
        """

        # TODO: test what happens when 3+ frames are passed

        if len(frames) == 0:
            frames = self.__query_frames()

        x = frames["pos_x"]
        y = frames["pos_y"]
        z = frames["pos_z"]

        return np.sqrt(np.sum(np.diff(x) ** 2, np.diff(y) ** 2, np.diff(z) ** 2))

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
            self.__marker_count,
            dtype=[("pos_x", "float"), ("pos_y", "float"), ("pos_z", "float")],
        )

        # Group by marker (every nth row where n is marker_count)
        for marker_idx in range(self.__marker_count):
            marker_data = frames[marker_idx :: self.__marker_count]

            # Calculate means for each coordinate
            means[marker_idx]["pos_x"] = np.mean(marker_data["pos_x"])
            means[marker_idx]["pos_y"] = np.mean(marker_data["pos_y"])
            means[marker_idx]["pos_z"] = np.mean(marker_data["pos_z"])

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

        if any(col not in header for col in ["frame", "pos_x", "pos_y", "pos_z"]):
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
                    else "int" if name == "frame" else "U32"
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
        last_frame = data["frame"][-1]
        lookback = last_frame - num_frames

        # Filter for relevant frames
        filtered_data = data[data["frame"] >= lookback]

        # Convert to centimeters
        coord_data = filtered_data.copy()
        for field in ["pos_x", "pos_y", "pos_z"]:
            coord_data[field] = coord_data[field] * 100.0

        return coord_data[["pos_x", "pos_y", "pos_z"]]
