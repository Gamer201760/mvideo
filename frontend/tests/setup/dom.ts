import { cleanup } from "@testing-library/react"
import { afterEach, beforeEach } from "vitest"
import { i18n } from "@/shared/i18n"
import { resetMotionEnvironment } from "./motionEnvironment"

beforeEach(async () => {
  await i18n.changeLanguage("ru")
})

afterEach(() => {
  cleanup()
  resetMotionEnvironment()
  localStorage.clear()
})
