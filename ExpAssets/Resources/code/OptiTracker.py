import os
import numpy as np


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
        velocity(): Calculate velocity based on marker positions
        position(): Get current position of markers
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

        self._sampling_rate = sample_rate
        self._data_dir = data_dir
        self._window_size = window_size

    @property
    def data_dir(self) -> str:
        """Get the data directory path."""
        return self.__data_dir

    @data_dir.setter
    def data_dir(self, data_dir: str) -> None:
        """Set the data directory path."""
        self.__data_dir = data_dir

    @property
    def sampling_rate(self) -> int:
        """Get the sampling rate."""
        return self.__sampling_rate

    @sampling_rate.setter
    def sampling_rate(self, sample_rate: int) -> None:
        """Set the sampling rate."""
        self.__sampling_rate = sample_rate

    @property
    def window_size(self) -> int:
        """Get the window size."""
        return self.__window_size

    @window_size.setter
    def window_size(self, window_size: int) -> None:
        """Set the window size."""
        self.__window_size = window_size

    def velocity(self) -> float:
        """Calculate and return the current velocity."""
        return self.__velocity()

    def position(self) -> np.ndarray:
        """Get the current position of markers."""
        frame = self.__query_frames(num_frames=1)
        return self.__column_means(frame)

    def __velocity(self) -> float:
        """
        Calculate velocity using position data over the specified window.

        Returns:
            float: Calculated velocity in cm/s
        """
        if self.__window_size < 2:
            raise ValueError("Window size must cover at least two frames.")

        frames = self.__query_frames()

        positions = self.__column_means(frames)

        euclidean_distance = self.__euclidean_distance(positions)

        velocity = euclidean_distance / (self.__window_size / self.__sampling_rate)

        return float(velocity)

    def __euclidean_distance(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate Euclidean distance between first and last frames.

        Args:
            frames (np.ndarray, optional): Array of frame data; will query the last window_size frames if not provided.

        Returns:
            float: Euclidean distance
        """

        if len(frames) == 0:
            frames = self.__query_frames()

        return float(np.linalg.norm(frames[0] - frames[-1]))

    def __column_means(self, frames: np.ndarray = np.array([])) -> np.ndarray:
        """
        Calculate column means of position data.

        Args:
            frames (np.ndarray, optional): Array of frame data; will query the last window_size frames if not provided.

        Returns:
            np.ndarray: Array of mean positions
        """

        if len(frames) == 0:
            frames = self.__query_frames()

        reshaped = frames.reshape(self.__marker_count, self.__window_size)

        frames = np.array(
            [], dtype=[("pos_x", "float"), ("pos_y", "float"), ("pos_z", "float")]
        )

        for frame in reshaped:
            x_vals = frame["pos_x"]
            y_vals = frame["pos_y"]
            z_vals = frame["pos_z"]

            np.append(
                frames, np.array([np.mean(x_vals), np.mean(y_vals), np.mean(z_vals)])
            )

        return frames

    def __query_frames(self, num_frames: int = 0) -> np.ndarray:
        """
        Query and process frame data from the data file.

        Args:
            num_frames (int, optional): Number of frames to query. Will default to window_size if not provided.

        Returns:
            np.ndarray: Array of queried frame data

        Raises:
            ValueError: If data directory is not set or data format is invalid
            FileNotFoundError: If data directory does not exist
        """
        if self.__data_dir == "":
            raise ValueError("No data directory was set.")

        if not os.path.exists(self.__data_dir):
            raise FileNotFoundError(f"Data directory not found at:\n{self.__data_dir}")

        with open(self.__data_dir, "r") as file:
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
            self.__data_dir, delimiter=",", dtype=dtype_map, skip_header=1
        )

        if num_frames == 0:
            num_frames = self.__window_size

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
