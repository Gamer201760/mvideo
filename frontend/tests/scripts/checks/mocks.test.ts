import { describe, expect, it } from "vitest"
import { mockWords, noMocks } from "../../../scripts/checks/rules/code/mocks.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text = "export const value = 1\n"): SourceFile => ({ path, text })

describe("no-mocks", () => {
  it("passes queries that call the api and test doubles outside src", () => {
    const query = [
      'import { api, unwrap } from "@/shared/api"',
      "export const usersQuery = {",
      '  queryKey: ["users"],',
      '  queryFn: () => unwrap(api.GET("/api/users")),',
      "  placeholderData: [],",
      "}",
    ].join("\n")
    const files = [
      file("src/entities/user/user.queries.ts", query),
      file("tests/entities/user/mocks.ts", "export const mockUser = { id: 1 }\n"),
      file("package.json", JSON.stringify({ devDependencies: { vitest: "4" } })),
    ]
    expect(noMocks.run(files)).toEqual([])
  })

  it.each([
    ["src/entities/user/mock-users.ts"],
    ["src/shared/api/__mocks__/client.ts"],
    ["src/features/search/fixtures/results.ts"],
    ["src/entities/order/order.fake.ts"],
  ])("reports a mock data file %s", (path) => {
    expect(noMocks.run([file(path)])).toHaveLength(1)
  })

  it("reports mock identifiers, mock servers and canned responses", () => {
    const text = [
      'import { setupWorker } from "msw/browser"',
      "export const MOCK_USERS = [{ id: 1 }]",
      "export const useMocks = import.meta.env.VITE_USE_MOCKS",
      "export const a = { queryFn: () => Promise.resolve([{ id: 1 }]) }",
      "export const b = { queryFn: async () => { return { total: 3 } } }",
      "export const c = { initialData: [{ id: 1 }] }",
      "export const worker = setupWorker",
    ].join("\n")
    const messages = noMocks.run([file("src/app/demo.ts", text)]).map((v) => v.message)
    expect(messages).toEqual([
      "msw/browser serves fake responses",
      "queryFn returns a canned response instead of calling the api",
      "queryFn returns a canned response instead of calling the api",
      "initialData with literal data",
      "mock identifier MOCK_USERS",
      "mock identifier useMocks",
      "mock identifier VITE_USE_MOCKS",
    ])
  })

  it("reports mock packages in every dependency group", () => {
    const manifest = JSON.stringify({
      dependencies: { react: "19" },
      devDependencies: { msw: "2", "@faker-js/faker": "9", "json-server": "1" },
    })
    expect(noMocks.run([file("package.json", manifest)])).toHaveLength(3)
  })

  it("splits identifiers into words before matching", () => {
    expect(mockWords("fakeApiClient")).toEqual(["fake"])
    expect(mockWords("USE_STUBBED_DATA")).toEqual(["stubbed"])
    expect(mockWords("stubbornValue")).toEqual([])
    expect(mockWords("fixtureLoader")).toEqual(["fixture"])
  })
})
