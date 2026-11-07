import { describe, expect, it } from 'vitest'
import { formatCurrency } from './format'

describe('synthetic financial amounts', () => {
  it('preserves cents above the safe integer range', () => {
    expect(formatCurrency('9999999999999999.99')).toBe('9,999,999,999,999,999.99')
  })
  it('formats whole values and decimal strings without inventing currency', () => {
    expect(formatCurrency('1234.50')).toBe('1,234.50')
    expect(formatCurrency('0')).toBe('0.00')
    expect(formatCurrency('12.999')).toBe('13.00')
  })
})
