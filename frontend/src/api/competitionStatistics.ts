import { api } from './client.ts'

export interface StatisticsQuery {
  year?: string
  form?: string
  group?: string
  membership?: string
}

export interface StatisticsGroup {
  id: string
  label: string
  unit_label: string
  method: string
  higher_better: boolean
  counted_shots: number | null
  maximum: number | null
  is_rings?: boolean
}

export interface Performance {
  count: number
  average: number | null
  member_average: number | null
  per_shot: number | null
  best: number | null
  best_names: string[]
  previous_year?: number
  previous_average?: number | null
  change?: number | null
}

export interface StatisticsMember {
  membership: number
  name: string
  starts: number
  wins: number
  podiums: number
  prizes: number
  count: number
  average: number | null
  best: number | null
}

export interface StatisticsResult {
  competition: number
  title: string
  date: string
  form: string
  own: boolean
  membership?: number
  name: string
  unit_name: string
  scoring?: string
  scoring_id?: number
  group?: string
  place?: number | null
  field?: number | null
  value?: number | null
  unit_label?: string
  prizes?: string[]
}

export interface CompetitionStatisticsData {
  years: number[]
  groups: StatisticsGroup[]
  selected_group: StatisticsGroup | null
  summary: {
    competitions: number
    members: number
    starts: number
    wins: number
    podiums: number
    prizes: number
    awards: number
    /** Starts derselben Wettbewerbe, die nicht zählen (nur in der Gesamtsicht) */
    not_counted?: { guests: number; out_of_competition: number; absent: number }
  }
  performance: Performance | null
  group_summary: (StatisticsGroup & Performance)[]
  buckets: {
    year: number
    starts: number
    members: number
    count: number
    average: number | null
  }[]
  members: StatisticsMember[]
  member_options?: { membership: number; name: string }[]
  results: StatisticsResult[]
  awards: {
    id: number
    year: number
    name: string
    title: string
    competition: number | null
    competition_title: string
  }[]
  can_open?: boolean
}

function queryString(query: StatisticsQuery) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) if (value) params.set(key, value)
  return params.size ? `?${params}` : ''
}

export const competitionStatisticsApi = {
  all: (org: number, query: StatisticsQuery) =>
    api.get<CompetitionStatisticsData>(
      `/api/orgs/${org}/competitions/statistics/${queryString(query)}`,
    ),
  member: (org: number, membership: number, query: StatisticsQuery) =>
    api.get<CompetitionStatisticsData>(
      `/api/orgs/${org}/competitions/member/${membership}/statistics/${queryString(query)}`,
    ),
  mine: (access: number, query: StatisticsQuery) =>
    api.get<CompetitionStatisticsData>(
      `/api/portal/${access}/competition-statistics/${queryString(query)}`,
    ),
}
