from math import sqrt

class Kinematics:
    """Class for calculating kinematic properties of a marker set."""
    def __init__(self, sample_rate: int = 120):
        self.sampling_rate = sample_rate
        pass

    def velocity(self, frames: list[tuple[float, float, float]]):
        if frames is None:
            raise ValueError("Frames must be provided for any computations to be performed.")

        demarkation_point = len(frames) // 2
        prev_pos = self.colwise_means(frames[0:demarkation_point])  # type: ignore[attr-defined]
        curr_pos = self.colwise_means(frames[demarkation_point:])  # type: ignore[attr-defined]

        travel = self.euclidean_distance(prev_pos, curr_pos)

        return self.derivate(delta=travel)

    def euclidean_distance(
        self,
        ref_pos: tuple[float, float, float],
        curr_pos: tuple[float, float, float],
    ):
        """Calculate Euclidean distance between two 3D points.

        Args:
            ref_pos (tuple[float, float, float]): Reference position (x, y, z).
            curr_pos (tuple[float, float, float]): Current position (x, y, z).

        Returns:
            float: Euclidean distance between the two points.
        """
        return sqrt(sum([(curr_pos[i] - ref_pos[i]) ** 2 for i in range(3)]))

    def colwise_means(
        self, frames: list[tuple[float, float, float]]
    ) -> tuple[float, float, float]:
        """Calculate column-wise means for a series of 3D coordinates.

        Args:
            frames (tuple[tuple[float, float, float]]): Series of (x, y, z) coordinates.

        Returns:
            tuple[float, float, float]: Mean (x, y, z) coordinates.

        Raises:
            ValueError: If any frame does not contain exactly 3 coordinates.
        """
        if not all(len(frame) == 3 for frame in frames):
            raise ValueError("Frames must be tuples containing xyz tuples.")

        # stack coords by transposing frames, then average columns
        col_means = tuple(sum(column) / len(frames) for column in zip(*frames))

        # ensure that the result is a tuple of 3 floats
        if len(col_means) != 3 or not all(
            isinstance(mean, float) for mean in col_means
        ):
            raise ValueError(
                "Expected to produce a tuple of 3 floats.\n"
                + f"Actual result was: {col_means}"
            )

        else:
            return col_means

    def derivate(self, delta: float) -> float:  # type: ignore[attr-defined]
        """Calculate time derivative of a value using sampling rate.

        Args:
            delta (float): Value to be converted to rate of change.

        Returns:
            float: Rate of change per second.
        """
        return delta / (1 / self.sampling_rate)
