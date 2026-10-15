import { createBrowserRouter } from "react-router"
import { lazyPage } from "./lazy-page"
import { RootError } from "./root-error/root-error"
import { RootLayout } from "./root-layout/root-layout"
import { RouteFallback } from "./route-fallback/route-fallback"

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <RootError />,
    hydrateFallbackElement: <RouteFallback />,
    children: [
      { index: true, lazy: lazyPage(() => import("@/pages/stand/stand-page"), "StandPage") },
      { path: "status", lazy: lazyPage(() => import("@/pages/home/home-page"), "HomePage") },
      {
        path: "*",
        lazy: lazyPage(() => import("@/pages/not-found/not-found-page"), "NotFoundPage"),
      },
    ],
  },
])
