from klibs import P
from math import sqrt

class Vectorizer:
    def __init__(self) -> None:
        return


    def get_velocity(self) -> float:
        for p in ['set_name', 'set_len', 'framerate']:
            if P.get(p) is None:
                raise ValueError(f'{p} not defined in _params')

        frames = self.__query_frames(2)

        demarkation = len(frames) // 2
        prev_pos = self.__colwise_means(frames[0:demarkation])
        curr_pos = self.__colwise_means(frames[demarkation:])

        travel = self.__euclidean_distance(prev_pos, curr_pos)

        return self.__derivate(travel)

    def __euclidean_distance(
        self,
        ref_pos: tuple[float, float, float],
        curr_pos: tuple[float, float, float],
    ):
        return sqrt(sum([(curr_pos[i] - ref_pos[i]) ** 2 for i in range(3)]))

    def __colwise_means(
        self, frames: tuple[tuple[float, float, float]]
    ) -> tuple[float, float, float]:

        if not all(len(frame) == 3 for frame in frames):
            raise ValueError('Frames must be xyz tuples.')

        # stack coords by transposing frames, then average columns
        return tuple(sum(column) / len(frames) for column in zip(*frames))

    def __derivate(self, value: float) -> float:
        return value / (1 / P.framerate)

