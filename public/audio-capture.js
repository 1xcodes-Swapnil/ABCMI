// AudioWorklet captures actual microphone PCM; no generated audio or transcript.
class PCMInput extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = new Float32Array(4096);
    this.count = 0;
    this.port.onmessage = event => {
      if (event.data === 'flush') {
        if (this.count) this.port.postMessage(this.samples.slice(0, this.count));
        this.count = 0;
        this.port.postMessage('flushed');
      }
    };
  }
  process(inputs) {
    const input = inputs[0];
    if (!input?.length) return true;
    for (let i = 0; i < input[0].length; i++) {
      let mono = 0;
      for (const channel of input) mono += channel[i] / input.length;
      this.samples[this.count++] = mono;
      if (this.count === this.samples.length) {
        this.port.postMessage(this.samples.slice());
        this.count = 0;
      }
    }
    return true;
  }
}
registerProcessor('abci-pcm-input', PCMInput);
