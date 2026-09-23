import type { Dataset, Plan } from './model'

/** Сравнение двух планов для сообщений в UI (логика планирования на backend). */
export function changesBetween(oldPlan: Plan, newPlan: Plan, data: Dataset): string[] {
  const oldStops = new Map(
    oldPlan.routes.flatMap((r) => r.stops.map((s) => [s.requestId, { engineerId: r.engineerId, start: s.plannedStart }] as const)),
  )
  const newStopIds = new Set(newPlan.routes.flatMap((route) => route.stops.map((stop) => stop.requestId)))
  const messages: string[] = []
  for (const route of newPlan.routes) {
    for (const stop of route.stops) {
      const old = oldStops.get(stop.requestId)
      const job = data.requests.find((r) => r.id === stop.requestId)
      if (!old) {
        messages.push(
          `${job?.priority === 'urgent' ? 'Срочная заявка' : 'Заявка'} #${stop.requestId} добавлена в маршрут ${data.engineers.find((e) => e.id === route.engineerId)?.name}`,
        )
      } else if (old.engineerId !== route.engineerId) {
        messages.push(`Заявка #${stop.requestId} передана ${data.engineers.find((e) => e.id === route.engineerId)?.name}`)
      } else if (old.start !== stop.plannedStart) {
        messages.push(`Заявка #${stop.requestId} перенесена на ${stop.plannedStart}`)
      }
    }
  }
  for (const [requestId] of oldStops) {
    if (!newStopIds.has(requestId)) {
      const job = data.requests.find((r) => r.id === requestId)
      messages.push(
        job?.status === 'cancelled'
          ? `Заявка #${requestId} отменена и снята с маршрута.`
          : `Заявка #${requestId} снята с маршрута после перепланирования.`,
      )
    }
  }
  return messages
}
