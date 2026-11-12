/// <reference types="vite/client" />

/** @type {import('react').FunctionComponent} */
declare module "*.css";

interface ImportMetaEnv {
  readonly VITE_OIDC_AUTHORITY?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;
  readonly VITE_MOBILE_BUILD?: string;
  readonly VITE_APP_STOREFRONT?: string;
  readonly VITE_APP_BASE_URL?: string;
  readonly VITE_APP_MOUNT_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
