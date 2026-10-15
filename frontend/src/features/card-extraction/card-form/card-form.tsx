import { type FormEvent, useState } from "react"
import type { ExtractInput, StandCategory, StandExample } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, Card, Select, TextField } from "@/shared/ui"
import { formatSellerLines, parseSellerLines } from "../seller-lines"
import styles from "./card-form.module.css"

export interface CardFormProps {
  readonly categories: readonly StandCategory[]
  readonly examples: readonly StandExample[]
  readonly pending: boolean
  readonly onSubmit: (input: ExtractInput) => void
}

export function CardForm({ categories, examples, pending, onSubmit }: CardFormProps) {
  const { t } = useTranslation()
  const [example, setExample] = useState<string | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [seller, setSeller] = useState("")
  const current = categories.find((c) => String(c.category_id) === category)
  const pathOf = (id: number) => categories.find((c) => c.category_id === id)?.name ?? ""

  const pickExample = (sku: string) => {
    const found = examples.find((e) => String(e.sku_id) === sku)
    if (found === undefined) return
    setExample(sku)
    setCategory(String(found.category_id))
    setTitle(found.title)
    setDescription(found.description)
    setSeller(formatSellerLines(found.seller_params))
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({
      title: title.trim(),
      description,
      seller_params: parseSellerLines(seller),
      category_id: current === undefined ? null : current.category_id,
    })
  }

  return (
    <Card title={t("stand:form.title")} motionIndex={0} className={styles.card}>
      <form className={styles.form} onSubmit={submit}>
        <Select
          label={t("stand:form.example")}
          placeholder={t("stand:form.examplePlaceholder")}
          value={example}
          onChange={pickExample}
          options={examples.map((e) => ({
            value: String(e.sku_id),
            label: e.title,
            hint: pathOf(e.category_id),
          }))}
        />
        <Select
          label={t("stand:form.category")}
          placeholder={t("stand:form.categoryPlaceholder")}
          value={category}
          onChange={setCategory}
          options={categories.map((c) => ({
            value: String(c.category_id),
            label: c.name,
            hint: t("stand:form.categoryHint", { count: c.attributes.length }),
          }))}
        />
        <TextField
          label={t("stand:form.titleField")}
          placeholder={t("stand:form.titlePlaceholder")}
          value={title}
          onChange={setTitle}
          required
        />
        <TextField
          label={t("stand:form.descriptionField")}
          placeholder={t("stand:form.descriptionPlaceholder")}
          value={description}
          onChange={setDescription}
          rows={6}
        />
        <TextField
          label={t("stand:form.seller")}
          placeholder={t("stand:form.sellerPlaceholder")}
          hint={t("stand:form.sellerHint")}
          value={seller}
          onChange={setSeller}
          rows={4}
          mono
        />
        <Button type="submit" icon="extract" pending={pending} disabled={title.trim() === ""}>
          {t("stand:form.submit")}
        </Button>
      </form>
    </Card>
  )
}
