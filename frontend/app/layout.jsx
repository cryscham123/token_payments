import "./globals.css";

export const metadata = {
  title: "Skkrypto Market",
  description: "암호화폐 결제 기능을 제공하는 마켓플레이스",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
