export default function manifest() {
  return {
    name: "Skkrypto Market",
    short_name: "Skkrypto",
    description: "암호화폐 결제 기능을 제공하는 마켓플레이스",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#1d4ed8",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
