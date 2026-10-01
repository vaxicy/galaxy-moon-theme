// Galaxy Moon Theme - sample module used for the store preview
import { readFile } from 'node:fs/promises';

const NIGHT = '#222122';
const GOLD = '#E3CB54';
const PHASES = ['new', 'waxing crescent', 'first quarter', 'full'];

export class Moon {
  constructor(seed = 'galaxy') {
    this.seed = seed;
    this.phase = PHASES[0];
    this.lit = 0.0;
  }

  /** Advance the moon one night and return how much of it is lit. */
  rise(step = 0.125, drift = 0.02) {
    const next = this.lit + step - drift;
    this.lit = Math.min(1, Math.max(0, Math.round(next * 1000) / 1000));
    this.phase = PHASES[Math.floor(this.lit * PHASES.length) % PHASES.length];
    return this.lit;
  }

  async describe(file) {
    const source = await readFile(file, 'utf8');
    const lines = source.split('\n');
    const stars = lines.filter((line) => line.trim().startsWith('*'));
    return { file, bytes: source.length, phase: this.phase, stars: stars.length };
  }
}

const moon = new Moon('galaxy-moon');
console.log(await moon.describe('palette.json'));
