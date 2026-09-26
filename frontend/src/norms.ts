export type WorkNorm = {
  id: string
  title: string
  travelMinutes: number
  technicalMinutes: number
  documentsMinutes: number
  totalMinutes: number
  skill: string
}

/** Справочник для UI; расчёт длительности при загрузке CSV выполняется на backend. */
export const workNorms: WorkNorm[] = [
  {
    id: 'connection',
    title: 'Подключение клиентов · базовая',
    travelMinutes: 20,
    technicalMinutes: 60,
    documentsMinutes: 10,
    totalMinutes: 90,
    skill: 'Работы на подключение и дозаказы',
  },
  {
    id: 'tkd-incident',
    title: 'Авария на ТКД',
    travelMinutes: 20,
    technicalMinutes: 80,
    documentsMinutes: 0,
    totalMinutes: 100,
    skill: 'Аварийные работы',
  },
  {
    id: 'equipment',
    title: 'Дозаказ оборудования',
    travelMinutes: 20,
    technicalMinutes: 10,
    documentsMinutes: 10,
    totalMinutes: 40,
    skill: 'Работы на подключение и дозаказы',
  },
  {
    id: 'local',
    title: 'Локальная заявка / ремонт у клиента',
    travelMinutes: 20,
    technicalMinutes: 30,
    documentsMinutes: 0,
    totalMinutes: 50,
    skill: 'Локальные работы',
  },
]
