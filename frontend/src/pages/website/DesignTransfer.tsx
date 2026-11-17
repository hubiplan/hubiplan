// Webseite › Gestaltung › „Design weitergeben“: ein Design als Paket (ZIP) speichern und
// Pakete als eigenes Design einspielen und freigeben (konzepte/designs-import-export.md,
// Ralf 2026-11-02). Seit #481 spielt jeder, der die Webseite verwaltet, Pakete für die
// eigene Einheit ein; für die ganze Installation und zum Sperren der Pakete einzelner
// Einheiten braucht es Plattformverwalter. HUBIplan prüft jedes Paket streng.
import { useEffect, useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { websiteApi } from '../../api/website.ts'
import type {
  DesignPackage,
  DesignPackageCheck,
  UnitDesignPackage,
  WebsiteData,
} from '../../api/website.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function DesignTransfer({
  data,
  design,
  onChanged,
}: {
  data: WebsiteData
  design: string
  onChanged: () => void
}) {
  const org = useActiveOrg()
  const designs = data.designs ?? []
  const [picked, setChosen] = useState<string | null>(null)
  const chosen = picked ?? design
  const [error, setError] = useState<string | null>(null)
  const siteUrl = data.website?.url ?? null
  const current = designs.find((d) => d.key === chosen) ?? designs[0]

  async function exportPackage() {
    setError(null)
    if (!current) return
    if (!current.package) {
      if (!siteUrl) {
        setError(t('Für den Export fehlt noch eine Domain der Webseite.'))
        return
      }
      // Standarddesigns kennt nur die Webseite selbst (CSS und Vorlagen)
      window.location.assign(`${siteUrl}design-paket/${encodeURIComponent(current.key)}.zip`)
      return
    }
    try {
      const blob = await websiteApi.exportDesign(org.id, current.key)
      saveBlob(blob, `design-${current.key}.zip`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <details className="design-roles design-transfer">
      <summary>{t('Design weitergeben')}</summary>
      <p className="muted small">
        {t(
          'Ein Designpaket enthält CSS, Farbrollen und die Auswahl eines gepflegten Standardlayouts. Es enthält keine eigenen HTML-Vorlagen, Wappen, Texte oder Bilder. Wer die Webseite verwaltet, kann es unter eigenem Namen für diese Einheit einspielen. Das Layout folgt den gepflegten Standardkomponenten.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid-2">
        <SelectField
          label={t('Design')}
          value={current?.key ?? ''}
          onChange={(e) => setChosen(e.target.value)}
        >
          {designs.map((d) => (
            <option key={d.key} value={d.key}>
              {d.package ? t('{label} (eigenes Design)', { label: d.label }) : d.label}
            </option>
          ))}
        </SelectField>
        <div className="field">
          <span aria-hidden="true">&nbsp;</span>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void exportPackage()}
          >
            {t('Als Paket speichern')}
          </button>
        </div>
      </div>
      {data.can_import_designs && (
        <DesignImport platform={data.designs_platform === true} onChanged={onChanged} />
      )}
      {data.designs_platform && <UnitPackages />}
    </details>
  )
}

function DesignImport({ platform, onChanged }: { platform: boolean; onChanged: () => void }) {
  const org = useActiveOrg()
  const [file, setFile] = useState<File | null>(null)
  const [inputKey, setInputKey] = useState(0)
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [labelEn, setLabelEn] = useState('')
  const [replace, setReplace] = useState(false)
  const [unitOnly, setUnitOnly] = useState(false)
  const [check, setCheck] = useState<DesignPackageCheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [packages, setPackages] = useState<DesignPackage[] | null>(null)

  async function loadPackages() {
    try {
      setPackages(await websiteApi.designPackages(org.id))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    let active = true
    websiteApi
      .designPackages(org.id)
      .then((list) => active && setPackages(list))
      .catch((err: unknown) => active && setError(errorMessage(err)))
    return () => {
      active = false
    }
  }, [org.id])

  async function send(onlyCheck: boolean) {
    if (!file) return
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const result = await websiteApi.importDesign(org.id, file, {
        key: key.trim(),
        label: label.trim(),
        label_en: labelEn.trim(),
        check: onlyCheck,
        replace,
        unit: !platform || unitOnly,
      })
      if (onlyCheck) {
        setCheck(result.package as DesignPackageCheck)
      } else {
        setDone(
          t('„{label}“ ist eingespielt und für diese Webseite freigegeben.', {
            label: result.package.label,
          }),
        )
        setCheck(null)
        setFile(null)
        setInputKey((k) => k + 1)
        setKey('')
        setLabel('')
        setLabelEn('')
        setReplace(false)
        await loadPackages()
        onChanged()
      }
    } catch (err) {
      setCheck(null)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function release(p: DesignPackage, released: boolean) {
    setError(null)
    try {
      await websiteApi.releaseDesign(org.id, p.key, released)
      await loadPackages()
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function remove(p: DesignPackage) {
    const ok = await confirmDialog({
      final: true,
      title: t('Designpaket „{label}“ löschen?', { label: p.label }),
      message: t(
        'Webseiten können es danach nicht mehr wählen. Eine Sicherung ist das gespeicherte Paket.',
      ),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    setError(null)
    try {
      await websiteApi.removeDesign(org.id, p.key)
      await loadPackages()
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <h3>{t('Design aus Paket laden')}</h3>
      <p className="muted small">
        {t(
          'Erlaubt sind CSS, Farbrollen und Standardlayouts. Freie HTML-/Django-Vorlagen werden abgelehnt. Alte Pakete mit freien Vorlagen zeigen Klassisch, bis sie durch ein Paket ohne Vorlagen ersetzt werden.',
        )}
      </p>
      <p className="muted small">
        {platform
          ? t(
              'Als Plattformverwalter spielt ihr ein Paket für die ganze Installation ein und gebt es je Webseite frei, oder nur für diese Einheit.',
            )
          : t(
              'Das Paket gilt nur für die Webseite dieser Einheit; andere Vereine sehen es nicht. Höchstens 10 eigene Designs, je Paket höchstens 2 MB.',
            )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {done && <Alert kind="success">{done}</Alert>}
      <div className="grid-2">
        <label className="field">
          <span>{t('Designpaket (ZIP)')}</span>
          <input
            key={inputKey}
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setCheck(null)
              setDone(null)
            }}
          />
        </label>
        <Field
          label={t('Kürzel')}
          value={key}
          onChange={(e) => setKey(e.target.value.toLowerCase())}
          hint={t('z. B. „hubertus“; leer = Kürzel aus dem Paket')}
          maxLength={31}
        />
        <Field
          label={t('Name')}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          hint={t('leer = Name aus dem Paket')}
          maxLength={60}
        />
        <Field
          label={t('Name auf Englisch')}
          value={labelEn}
          onChange={(e) => setLabelEn(e.target.value)}
          maxLength={60}
        />
      </div>
      {check && (
        <Alert kind="info">
          {t('Paket in Ordnung: „{label}“ ({key}).', { label: check.label, key: check.key })}{' '}
          {t('Standardlayout mit eigener Gestaltung.')}{' '}
          {check.source &&
            t('Die Farbzuordnung von „{source}“ wird übernommen.', { source: check.source })}
          {check.warnings.map((w) => (
            <span key={w}>
              <br />
              {w}
            </span>
          ))}
        </Alert>
      )}
      {platform && (
        <Checkbox
          label={t('nur für diese Einheit')}
          checked={unitOnly}
          onChange={(value) => {
            setUnitOnly(value)
            setCheck(null)
          }}
        />
      )}
      {check?.exists && (
        <Checkbox
          label={t('Vorhandenes Design mit diesem Kürzel ersetzen')}
          checked={replace}
          onChange={setReplace}
        />
      )}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          disabled={!file || busy}
          onClick={() => void send(true)}
        >
          {t('Prüfen')}
        </button>
        <button
          type="button"
          className="button"
          disabled={!file || busy || !check || (check.exists && !replace)}
          onClick={() => void send(false)}
        >
          {t('Einspielen')}
        </button>
      </div>
      {packages && packages.length > 0 && (
        <>
          <h3>{t('Eingespielte Designs')}</h3>
          <ul className="plain-list">
            {packages.map((p) => (
              <li key={p.key}>
                <strong>{p.label}</strong> <span className="muted small">({p.key})</span>{' '}
                <span className="muted small">
                  {p.scope === 'unit' ? t('nur diese Einheit') : t('ganze Installation')}
                </span>
                {p.blocked && (
                  <Alert kind="error">
                    {t(
                      'Plattformverwalter haben dieses Design gesperrt. Die Webseite zeigt Klassisch.',
                    )}
                  </Alert>
                )}
                {p.templates.length > 0 && (
                  <Alert kind="error">
                    {t(
                      'Dieses Paket ist wegen freier Vorlagen gesperrt. Die Webseite zeigt Klassisch. Bitte ein Paket ohne Vorlagen einspielen.',
                    )}
                  </Alert>
                )}
                <Checkbox
                  label={t('für diese Webseite freigegeben')}
                  checked={p.released}
                  disabled={p.in_use || p.can_change === false}
                  hint={p.in_use ? t('wird hier genutzt') : undefined}
                  onChange={(value) => void release(p, value)}
                />
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={p.in_use || p.can_change === false}
                  onClick={() => void remove(p)}
                >
                  {t('Löschen')}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

/** Plattformverwalter: Designs, die Einheiten selbst eingespielt haben, prüfen und sperren */
function UnitPackages() {
  const org = useActiveOrg()
  const [packages, setPackages] = useState<UnitDesignPackage[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    websiteApi
      .unitDesignPackages(org.id)
      .then((list) => active && setPackages(list))
      .catch((err: unknown) => active && setError(errorMessage(err)))
    return () => {
      active = false
    }
  }, [org.id])

  async function block(p: UnitDesignPackage, blocked: boolean) {
    setError(null)
    try {
      const next = await websiteApi.blockUnitDesign(org.id, p.id, blocked)
      setPackages((list) => list?.map((x) => (x.id === next.id ? next : x)) ?? null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (!error && (!packages || packages.length === 0)) return null
  return (
    <>
      <h3>{t('Designs der Einheiten')}</h3>
      <p className="muted small">
        {t(
          'Diese Designs haben Einheiten selbst eingespielt. Ein gesperrtes Design zeigt keine Webseite mehr; wer es nutzt, sieht Klassisch.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <ul className="plain-list">
        {(packages ?? []).map((p) => (
          <li key={p.id}>
            <strong>{p.label}</strong> <span className="muted small">({p.key})</span>{' '}
            <span className="muted small">{p.unit}</span>
            <Checkbox
              label={t('gesperrt')}
              checked={p.blocked}
              onChange={(value) => void block(p, value)}
            />
          </li>
        ))}
      </ul>
    </>
  )
}
