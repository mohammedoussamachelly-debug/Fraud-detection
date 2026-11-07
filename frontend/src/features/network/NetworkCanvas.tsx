import cytoscape, { type Core } from 'cytoscape'
import { useEffect, useRef } from 'react'
import type { AccountNeighborhood } from '../../api/types'
import { Button } from '../../components/ui/button'

export function NetworkCanvas({
  graph,
  selectedAccount,
  onSelect,
}: {
  graph: AccountNeighborhood
  selectedAccount: string
  onSelect: (id: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const instance = useRef<Core>()
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  useEffect(() => {
    if (!container.current) return
    const styles = getComputedStyle(document.documentElement)
    const color = (name: string) => styles.getPropertyValue(name).trim()
    const cy = cytoscape({
      container: container.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: {
            id: node.id,
            label: node.external_ref.includes('DEMO:')
              ? node.external_ref.split(':').slice(2).join(':')
              : node.external_ref,
          },
        })),
        ...graph.edges.map((edge) => ({
          data: { id: edge.transaction_id, source: edge.source, target: edge.target },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': color('--color-accent'),
            label: 'data(label)',
            color: color('--color-foreground'),
            'font-size': 11,
            'text-valign': 'bottom',
            'text-margin-y': 8,
            'text-wrap': 'wrap',
            'text-max-width': '70px',
            width: 26,
            height: 26,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': color('--color-foreground-subtle'),
            'target-arrow-color': color('--color-foreground-subtle'),
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
          },
        },
        {
          selector: ':selected',
          style: { 'border-width': 3, 'border-color': color('--color-foreground') },
        },
      ],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 35,
        spacingFactor: 1.4,
        nodeDimensionsIncludeLabels: true,
      },
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.2,
    })
    instance.current = cy
    cy.on('tap', 'node', (event) => selectRef.current(String(event.target.id())))
    const resize = new ResizeObserver(() => {
      cy.resize()
      cy.fit(undefined, 35)
    })
    resize.observe(container.current)
    const theme = new MutationObserver(() => {
      const css = getComputedStyle(document.documentElement)
      cy.style()
        .selector('node')
        .style({
          color: css.getPropertyValue('--color-foreground').trim(),
          'background-color': css.getPropertyValue('--color-accent').trim(),
        })
        .update()
    })
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      resize.disconnect()
      theme.disconnect()
      cy.destroy()
      instance.current = undefined
    }
  }, [graph])
  useEffect(() => {
    const cy = instance.current
    if (!cy) return
    cy.nodes().unselect()
    cy.getElementById(selectedAccount).select()
  }, [selectedAccount, graph])
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <p className="text-xs text-foreground-muted">
          Arrows show transfer direction · select an account below or in the graph
        </p>
        <Button size="sm" onClick={() => instance.current?.fit(undefined, 35)}>
          Fit graph
        </Button>
      </div>
      <div
        ref={container}
        className="h-[360px] sm:h-[460px]"
        role="img"
        aria-label={`Directed network of ${graph.nodes.length} accounts and ${graph.edges.length} transactions. Use the account list below for keyboard selection.`}
      />
    </div>
  )
}
