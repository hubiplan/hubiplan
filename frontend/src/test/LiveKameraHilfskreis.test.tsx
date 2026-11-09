// Live-Kamera: Hilfslinie um das Schwarze zusätzlich zum äußersten Ring (Ralf 09.11.).
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LiveCamera } from '../pages/competitions/LiveCamera.tsx'

function circles(blackShare: number) {
  const { container } = render(
    <LiveCamera blackShare={blackShare} onCapture={vi.fn()} onClose={vi.fn()} onFail={vi.fn()} />,
  )
  return Array.from(container.querySelectorAll('.live-guide circle'))
}

describe('Live-Kamera: Hilfskreise', () => {
  it('zeichnet den äußersten Ring und die Linie um das Schwarze', () => {
    // LG DSB: Spiegel 30,5 mm, äußerster Ring 45,5 mm
    const list = circles(30.5 / 45.5)
    expect(list).toHaveLength(2)
    const outer = Number(list[0].getAttribute('r'))
    const black = Number(list[1].getAttribute('r'))
    expect(list[1].getAttribute('class')).toBe('live-guide-black')
    expect(black / outer).toBeCloseTo(30.5 / 45.5, 5)
  })

  it('ohne sinnvollen Anteil nur der äußere Kreis', () => {
    expect(circles(1)).toHaveLength(1)
  })
})

describe('Live-Kamera: Karte mit fünf Spiegeln', () => {
  it('zeichnet keine festen Hilfskreise, sondern erst die erkannten Spiegel', () => {
    const { container } = render(
      <LiveCamera
        blackShare={29 / 38}
        spots={5}
        onCapture={vi.fn()}
        onClose={vi.fn()}
        onFail={vi.fn()}
      />,
    )
    expect(container.querySelectorAll('.live-guide circle')).toHaveLength(0)
  })
})
