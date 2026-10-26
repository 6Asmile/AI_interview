import { onUnmounted, ref } from 'vue';

export function useStreamingPcm() {
  const isPlaying = ref(false);
  const firstChunkMs = ref<number | null>(null);
  const lastCancelLatencyMs = ref<number | null>(null);
  let context: AudioContext | null = null;
  let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  let nextStart = 0;
  const sources = new Set<AudioBufferSourceNode>();

  const ensureContext = async (sampleRate: number) => {
    if (!context || context.state === 'closed') context = new AudioContext({ sampleRate });
    if (context.state === 'suspended') await context.resume();
    return context;
  };

  const cancel = () => {
    const started = performance.now();
    activeReader?.cancel().catch(() => undefined);
    activeReader = null;
    sources.forEach(source => { try { source.stop(); } catch { /* already ended */ } });
    sources.clear();
    nextStart = 0;
    isPlaying.value = false;
    lastCancelLatencyMs.value = performance.now() - started;
  };

  const play = async (response: Response, requestedAt: number, onFirstChunk?: (latencyMs: number) => void) => {
    cancel();
    const reader = response.body!.getReader();
    activeReader = reader;
    const sampleRate = Number(response.headers.get('X-Speech-Sample-Rate') || 24000);
    const audioContext = await ensureContext(sampleRate);
    isPlaying.value = true;
    firstChunkMs.value = null;
    nextStart = audioContext.currentTime + 0.035;
    let carry = new Uint8Array();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const merged = new Uint8Array(carry.length + value.length);
        merged.set(carry); merged.set(value, carry.length);
        const evenLength = merged.length - (merged.length % 2);
        carry = merged.slice(evenLength);
        if (!evenLength) continue;
        const view = new DataView(merged.buffer, merged.byteOffset, evenLength);
        const samples = new Float32Array(evenLength / 2);
        for (let index = 0; index < samples.length; index += 1) samples[index] = view.getInt16(index * 2, true) / 32768;
        const buffer = audioContext.createBuffer(1, samples.length, sampleRate);
        buffer.copyToChannel(samples, 0);
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        sources.add(source);
        source.onended = () => sources.delete(source);
        source.start(Math.max(audioContext.currentTime + 0.015, nextStart));
        nextStart = Math.max(audioContext.currentTime + 0.015, nextStart) + buffer.duration;
        if (firstChunkMs.value === null) {
          firstChunkMs.value = performance.now() - requestedAt;
          onFirstChunk?.(firstChunkMs.value);
        }
      }
      const remainingMs = Math.max(0, (nextStart - audioContext.currentTime) * 1000);
      await new Promise(resolve => window.setTimeout(resolve, remainingMs));
    } finally {
      if (activeReader === reader) {
        activeReader = null;
        isPlaying.value = false;
      }
    }
  };

  onUnmounted(() => { cancel(); context?.close(); });
  return { isPlaying, firstChunkMs, lastCancelLatencyMs, play, cancel };
}
