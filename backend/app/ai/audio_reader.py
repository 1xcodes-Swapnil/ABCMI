"""Seekable bounded audio reads, without loading a recording into RAM."""
import math


class AudioWindowReader:
    """Use SoundFile first; decode only the requested interval with PyAV otherwise."""

    def __init__(self, path):
        import soundfile as sf
        self.path, self._source, self._position = str(path), None, 0
        try:
            self._source = sf.SoundFile(path)
            self.samplerate, self.channels = self._source.samplerate, self._source.channels
            self.frames = len(self._source)
        except sf.LibsndfileError:
            import av
            with av.open(self.path) as container:
                stream = next(iter(container.streams.audio), None)
                if stream is None:
                    raise ValueError("No audio stream")
                self.samplerate = stream.codec_context.sample_rate
                self.channels = stream.codec_context.channels
                duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                            else float(container.duration / av.time_base) if container.duration is not None else None)
                if not duration or not math.isfinite(duration) or not self.samplerate or not self.channels:
                    raise ValueError("Audio stream lacks usable duration/rate/channels")
                self.frames = round(duration * self.samplerate)

    def __len__(self):
        return self.frames

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._source is not None:
            self._source.close()

    def seek(self, frame):
        self._position = max(0, min(int(frame), self.frames))
        if self._source is not None:
            self._source.seek(self._position)

    def read(self, frames, dtype="float32", always_2d=True):
        if frames < 0:
            raise ValueError("Unbounded audio reads are forbidden")
        if self._source is not None:
            return self._source.read(frames, dtype=dtype, always_2d=always_2d)
        import av
        import numpy as np
        first, last = self._position, min(self.frames, self._position + int(frames))
        pieces, cursor = [], first
        with av.open(self.path) as container:
            stream = container.streams.audio[0]
            origin = float((stream.start_time or 0) * stream.time_base)
            # AAC/Opus decoders need earlier real packets to rebuild their
            # overlap state. Decode preroll but retain only requested samples.
            seek_time = max(0.0, first / self.samplerate - 1.0) + origin
            if seek_time > origin:
                container.seek(int(seek_time / stream.time_base), stream=stream, backward=True)
            converter = av.AudioResampler(format="fltp", layout=stream.codec_context.layout, rate=self.samplerate)
            for frame in container.decode(stream):
                for converted in converter.resample(frame):
                    if converted.pts is None or converted.time_base is None:
                        raise RuntimeError("Compressed audio has no timestamps for accurate window slicing")
                    start = round((float(converted.pts * converted.time_base) - origin) * self.samplerate)
                    end = start + converted.samples
                    if start >= last:
                        break
                    left, right = max(cursor, start), min(last, end)
                    if right > left:
                        if left > cursor + 1:
                            raise RuntimeError("Compressed audio window contains a timestamp gap")
                        data = converted.to_ndarray().T
                        pieces.append(data[left-start:right-start])
                        cursor = right
                if cursor >= last or (frame.time is not None and frame.time - origin >= last / self.samplerate):
                    break
        if not pieces:
            raise RuntimeError("Compressed audio window decoded no actual samples")
        self._position = cursor
        result = np.concatenate(pieces, axis=0).astype(dtype, copy=False)
        return result if always_2d or self.channels != 1 else result[:, 0]
