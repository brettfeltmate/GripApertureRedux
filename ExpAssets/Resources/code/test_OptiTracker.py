import pytest
import numpy as np
from OptiTracker import OptiTracker
from textwrap import dedent


@pytest.fixture
def sample_data_file(tmp_path):

    data_content = dedent(
        """
        frame_number,pos_x,pos_y,pos_z
        1,0.0,0.0,0.0
        1,1.0,1.0,1.0
        1,2.0,2.0,2.0
        2,1.0,1.0,1.0
        2,2.0,2.0,2.0
        2,3.0,3.0,3.0
        3,2.0,2.0,2.0
        3,3.0,3.0,3.0
        3,4.0,4.0,4.0
        4,3.0,3.0,3.0
        4,4.0,4.0,4.0
        4,5.0,5.0,5.0
        5,4.0,4.0,4.0
        5,5.0,5.0,5.0
        5,6.0,6.0,6.0
        6,5.0,5.0,5.0
        6,6.0,6.0,6.0
        6,7.0,7.0,7.0
        7,6.0,6.0,6.0
        7,7.0,7.0,7.0
        7,8.0,8.0,8.0
        8,7.0,7.0,7.0
        8,8.0,8.0,8.0
        8,9.0,9.0,9.0
        9,8.0,8.0,8.0
        9,9.0,9.0,9.0
        9,10.0,10.0,10.0
        10,9.0,9.0,9.0
        10,10.0,10.0,10.0
        10,11.0,11.0,11.0
        """
    ).strip()
    data_file = tmp_path / "test_data.csv"
    data_file.write_text(data_content)
    return str(data_file)


@pytest.fixture
def tracker(sample_data_file):
    tracker = OptiTracker(marker_count=3, sample_rate=120, window_size=5)
    tracker.data_dir = sample_data_file
    return tracker


def test_init():
    tracker = OptiTracker(marker_count=3)
    assert tracker.sample_rate == 120
    assert tracker.window_size == 5
    assert tracker.marker_count == 3


def test_property_setters(tracker):
    tracker.sample_rate = 60
    assert tracker.sample_rate == 60

    tracker.window_size = 10
    assert tracker.window_size == 10

    new_path = "/new/path"
    tracker.data_dir = new_path
    assert tracker.data_dir == new_path


def test_invalid_data_dir():
    tracker = OptiTracker(marker_count=1)
    tracker.data_dir = ""
    with pytest.raises(ValueError, match="No data directory was set."):
        tracker.position()


def test_nonexistent_data_dir():
    tracker = OptiTracker(marker_count=1)
    tracker.data_dir = "/nonexistent/path"
    with pytest.raises(FileNotFoundError):
        tracker.position()


def test_position(tracker):
    position = tracker.position()
    assert isinstance(position, np.ndarray)
    assert position.dtype.names == ("frame_number", "pos_x", "pos_y", "pos_z")
    assert position["pos_x"].item() == 10.0
    assert position["pos_y"].item() == 10.0
    assert position["pos_z"].item() == 10.0


def test_velocity_invalid_window():
    tracker = OptiTracker(marker_count=1)
    with pytest.raises(ValueError, match="Window size must cover at least two frames."):
        tracker.velocity(num_frames=1)


def test_velocity(tracker):
    velocity = tracker.velocity(num_frames=2)
    assert isinstance(velocity, float)
    assert velocity == (np.sqrt(3) / (1 / 120))

    velocity = tracker.velocity()
    assert isinstance(velocity, float)
    assert velocity == (np.sqrt(12) / (1 / 120))


def test_distance(tracker):
    distance = tracker.distance(num_frames=2)
    assert isinstance(distance, float)
    assert distance == np.sqrt(3)

    distance = tracker.distance()
    assert isinstance(distance, float)
    assert distance == np.sqrt(12)


def test_invalid_data_format(tmp_path):
    invalid_data = dedent(
        """
        frame,invalid_x,invalid_y,invalid_z
        1,0.1,0.2,0.3
        """
    ).strip()
    data_file = tmp_path / "invalid_data.csv"
    data_file.write_text(invalid_data)

    tracker = OptiTracker(marker_count=1)
    tracker.data_dir = str(data_file)

    with pytest.raises(
        ValueError,
        match="Data file must contain columns named frame, pos_x, pos_y, pos_z.",
    ):
        tracker.position()
