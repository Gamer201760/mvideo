import { type Check, sourceScripts, type Violation } from "../../types.ts"

const PAGE = /^src\/pages\/.+-page\.tsx$/
const TITLE_CALL = /\buseDocumentTitle\(/

export const pageTitles: Check = {
  id: "page-titles",
  run: (files) =>
    sourceScripts(files)
      .filter((file) => PAGE.test(file.path) && !TITLE_CALL.test(file.text))
      .map(
        (file): Violation => ({
          file: file.path,
          message:
            "page sets no tab title: call useDocumentTitle(t(...)), or useDocumentTitle(null) on the home page",
        }),
      ),
}
