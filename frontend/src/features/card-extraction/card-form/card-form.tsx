import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react"
import type { ExtractInput, StandCategory, StandExample } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, Card, Disclosure, Segmented, Select, TextField } from "@/shared/ui"
import { readDraft, saveDraft } from "../card-storage"
import { SellerLineErrors } from "../seller-line-errors/seller-line-errors"
import { formatSellerLines, parseSellerLines } from "../seller-lines"
import styles from "./card-form.module.css"

type Engine = ExtractInput["engine"] & string

export interface CardFormProps {
  readonly categories: readonly StandCategory[]
  readonly examples: readonly StandExample[]
  readonly pending: boolean
  readonly onSubmit: (input: ExtractInput) => void
}

function submitOnShortcut(event: KeyboardEvent<HTMLFormElement>) {
  if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return
  event.preventDefault()
  event.currentTarget.requestSubmit()
}

export function CardForm({ categories, examples, pending, onSubmit }: CardFormProps) {
  const { t } = useTranslation()
  const [draft] = useState(readDraft)
  const [engine, setEngine] = useState<Engine>(draft.engine)
  const [example, setExample] = useState<string | null>(null)
  const [category, setCategory] = useState<string | null>(draft.category)
  const [title, setTitle] = useState(draft.title)
  const [description, setDescription] = useState(draft.description)
  const [seller, setSeller] = useState(draft.seller)
  const [detailsOpen, setDetailsOpen] = useState(draft.seller.trim() !== "")
  const [sellerChecked, setSellerChecked] = useState(draft.seller.trim() !== "")
  const [invalidSubmit, setInvalidSubmit] = useState(0)
  const sellerRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)
  const sellerLines = parseSellerLines(seller)
  useEffect(() => {
    if (invalidSubmit > 0) sellerRef.current?.focus()
  }, [invalidSubmit])
  useEffect(() => {
    saveDraft({ engine, category, title, description, seller })
  }, [engine, category, title, description, seller])
  const current = categories.find((c) => String(c.category_id) === category)
  const pathOf = (id: number) => categories.find((c) => c.category_id === id)?.name ?? ""

  const pickExample = (sku: string) => {
    const found = examples.find((e) => String(e.sku_id) === sku)
    if (found === undefined) return
    setExample(sku)
    setCategory(engine === "rules" ? String(found.category_id) : null)
    setTitle(found.title)
    setDescription(found.description)
    setSeller(formatSellerLines(found.seller_params))
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (title.trim() === "" || pending) return
    if (sellerLines.issues.length > 0) {
      setSellerChecked(true)
      setDetailsOpen(true)
      setInvalidSubmit((value) => value + 1)
      return
    }
    onSubmit({
      engine,
      title: title.trim(),
      description,
      seller_params: sellerLines.params,
      category_id: current === undefined ? null : current.category_id,
    })
  }

  return (
    <Card title={t("stand:form.title")} motionIndex={0} className={styles.card}>
      <form className={styles.form} onSubmit={submit} onKeyDown={submitOnShortcut}>
        <TextField
          className={styles.title}
          label={t("stand:form.titleField")}
          placeholder={t("stand:form.titlePlaceholder")}
          value={title}
          onChange={(value) => {
            setTitle(value)
            setExample(null)
          }}
          required
        />
        <TextField
          className={styles.description}
          label={t("stand:form.descriptionField")}
          placeholder={t("stand:form.descriptionPlaceholder")}
          value={description}
          onChange={(value) => {
            setDescription(value)
            setExample(null)
          }}
          rows={9}
        />
        <div className={styles.example}>
          <span className={styles.label}>{t("stand:form.example")}</span>
          <div className={styles.suggestions}>
            {examples.map((item) => (
              <Button
                key={item.sku_id}
                variant={example === String(item.sku_id) ? "secondary" : "ghost"}
                icon={example === String(item.sku_id) ? "check" : "card"}
                aria-label={t("stand:form.useExample", { title: item.title })}
                aria-pressed={example === String(item.sku_id)}
                title={item.title}
                onClick={() => pickExample(String(item.sku_id))}
              >
                {pathOf(item.category_id) || item.title}
              </Button>
            ))}
          </div>
        </div>
        <Disclosure
          className={styles.details}
          label={t("stand:form.details")}
          hint={t("stand:form.detailsHint")}
          open={detailsOpen}
          onOpenChange={setDetailsOpen}
        >
          <div className={styles.field}>
            <span className={styles.label} aria-hidden="true">
              {t("stand:form.engine")}
            </span>
            <Segmented<Engine>
              label={t("stand:form.engine")}
              value={engine}
              onChange={(value) => {
                setEngine(value)
                setCategory(null)
              }}
              options={[
                { value: "hybrid", label: t("stand:form.hybrid") },
                { value: "rules", label: t("stand:form.rules") },
              ]}
            />
          </div>
          <Select
            label={t("stand:form.category")}
            placeholder={t("stand:form.categoryPlaceholder")}
            value={category}
            onChange={setCategory}
            options={[
              { value: "auto", label: t("stand:form.categoryAuto") },
              ...categories.map((c) => ({
                value: String(c.category_id),
                label: c.name,
                hint: t("stand:form.categoryHint", { count: c.attributes.length }),
              })),
            ]}
          />
          <TextField
            label={t("stand:form.seller")}
            placeholder={t("stand:form.sellerPlaceholder")}
            hint={t("stand:form.sellerHint")}
            value={seller}
            onChange={setSeller}
            onBlur={() => setSellerChecked(true)}
            controlRef={sellerRef}
            error={
              sellerChecked && sellerLines.issues.length > 0 ? (
                <SellerLineErrors issues={sellerLines.issues} />
              ) : undefined
            }
            rows={4}
            mono
          />
        </Disclosure>
        <div className={styles.submit}>
          <span className={styles.shortcut}>{t("stand:form.submitHint")}</span>
          <Button type="submit" icon="extract" pending={pending} disabled={title.trim() === ""}>
            {t("stand:form.submit")}
          </Button>
        </div>
      </form>
    </Card>
  )
}
