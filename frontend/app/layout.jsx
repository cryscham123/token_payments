import "./globals.css";

export const metadata = {
  title: "Token Payments Storefront",
  description: "Crypto checkout storefront for Token Payments"
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
