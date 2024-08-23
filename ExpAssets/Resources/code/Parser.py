from collections.abc import Container

from construct import CString, Float32l, Int16sl, Int32ul, Struct, Computed, Default


def decode_marker_id(obj):
    return obj.encoded_id & 0x0000FFFF


def decode_model_id(obj):
    return obj.encoded_id >> 16


def decode_tracking_validity(obj):
    return (obj.tracking_valid & 0x01) != 0


class Parser(object):
    def __init__(self, data: bytes) -> None:
        self.data = memoryview(data)
        self.current_position_in_stream = 0

        self._structs = {
            'prefix': Int32ul,
            'label': CString('utf8'),
            'id': Int32ul,
            'count': Int32ul,
            'size': Int32ul,
            'marker': Struct(
                'x_pos' / Float32l, 'y_pos' / Float32l, 'z_pos' / Float32l
            ),
            'rigid_body': Struct(
                'parent_id' / Computed(None)  # NOTE: overwritten when unpacking parent structs
                'id' / Int32ul,
                'x_pos' / Float32l,
                'y_pos' / Float32l,
                'z_pos' / Float32l,
                'w_rot' / Float32l,
                'x_rot' / Float32l,
                'y_rot' / Float32l,
                'z_rot' / Float32l,
                'error' / Float32l,
                'valid' / Computed(Int16sl * decode_tracking_validity),
            ),
        }

        self.frame_number = self.unpack('prefix')

    def seek_ahead(self, skip: int) -> None:
        self.current_position_in_stream += skip

    def skip_asset(self) -> None:
        packet_size = self.unpack('size')
        self.seek_ahead(skip=packet_size)

    # TODO:
    # Confirm whether packet size defines whole asset
    # (i.e all markers within a given set)
    # if so, count argument is superfluous
    def sizeof(self, asset_type: str, count: int = 1) -> int:
        return self._structs[asset_type].sizeof() * count

    # FIXME: ids incorrectly decoded
    def decode_id(self, encoded_id: bytes) -> tuple[int, int]:
        tmp_id = Int32ul.parse(encoded_id)
        model_id = tmp_id >> 16
        marker_id = tmp_id & 0x0000FFFF

        return model_id, marker_id

    def unpack(
        self, asset_type: str
    ) -> Container[str | int | float] | int | str:

        unpacked = self._structs[asset_type].parse(
            self.data[self.current_position_in_stream :]
        )

        unpacked.update({'frame': self.frame_number})

        if asset_type == 'label':  # only asset type of unfixed length
            self.seek_ahead(skip=len(unpacked) + 1)
        else:
            self.seek_ahead(skip=self.sizeof(asset_type))

        return unpacked
