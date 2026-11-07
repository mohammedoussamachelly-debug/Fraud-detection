import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
const css = readFileSync('src/index.css', 'utf8')

function declarations(block: string): Record<string, string> {
  return Object.fromEntries(
    [...block.matchAll(/(--color-[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]),
  )
}
const palette = declarations(css.match(/@theme\s*\{([^}]+)\}/)![1])
const light = declarations(css.match(/:root\s*\{([^}]+)\}/)![1])
const dark = declarations(css.match(/:root\[data-theme=['"]dark['"]\]\s*\{([^}]+)\}/)![1])
function rgb(value: string): number[] {
  return [1, 3, 5].map((index) => parseInt(value.slice(index, index + 2), 16) / 255)
}
function luminance(color: number[]) {
  return color
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((sum, channel, i) => sum + channel * [0.2126, 0.7152, 0.0722][i], 0)
}
function contrast(a: number[], b: number[]) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (values[0] + 0.05) / (values[1] + 0.05)
}
for (const [name, theme] of Object.entries({ light, dark })) {
  describe(`${name} theme contrast`, () => {
    const tokens = { ...palette, ...light, ...theme }
    const resolve = (name: string): string => {
      const value = tokens[`--color-${name}`]
      return value.startsWith('var(') ? resolve(value.slice(12, -1)) : value
    }
    it('keeps body, metadata, and action text at AA on both surfaces', () => {
      for (const foreground of ['foreground', 'foreground-muted', 'foreground-subtle', 'accent']) {
        for (const background of ['surface', 'background']) {
          expect(
            contrast(rgb(resolve(foreground)), rgb(resolve(background))),
            `${foreground} on ${background}`,
          ).toBeGreaterThanOrEqual(4.5)
        }
      }
    })
    it('keeps semantic badge labels at AA on their translucent backgrounds', () => {
      for (const [tone, background] of Object.entries({
        info: 'blue-500',
        attention: 'amber-500',
        positive: 'green-500',
        negative: 'red-500',
        pending: 'violet-500',
      })) {
        const mixed = rgb(resolve(background)).map(
          (channel, index) => channel * 0.15 + rgb(resolve('surface'))[index] * 0.85,
        )
        expect(contrast(rgb(resolve(`status-${tone}`)), mixed), tone).toBeGreaterThanOrEqual(4.5)
      }
    })
    it('keeps input boundaries and focus indications at 3:1', () => {
      for (const token of ['border-strong', 'accent'])
        expect(
          contrast(rgb(resolve(token)), rgb(resolve('surface'))),
          token,
        ).toBeGreaterThanOrEqual(3)
    })
  })
}
