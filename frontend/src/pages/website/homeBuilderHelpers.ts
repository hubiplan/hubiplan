// Gemeinsame Helfer, Typen und Konstanten von HomeBuilder.
import type { HomeItem, HomeTile } from '../../api/website.ts'

export function emptyTile(): HomeTile {
  return { title: '', text: '', image: null, target: null }
}

export const emptyPartner = (): HomeItem => ({ name: '', image: null, url: '' })
export const emptyFact = (): HomeItem => ({ value: '', label: '' })
export const emptyHours = (): HomeItem => ({ day: '', time: '', note: '' })
export const emptyStation = (): HomeItem => ({ when: '', title: '', text: '' })
export const emptyProgram = (): HomeItem => ({ day: '', time: '', text: '' })
export const emptyPicture = (): HomeItem => ({ image: null, caption: '' })
