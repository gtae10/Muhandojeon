export default function Footer() {
  return (
    <>
      <footer className="border-t border-[var(--color-border)] bg-[var(--color-surface)] px-4 sm:px-6 py-8">
        <div className="max-w-[720px] mx-auto w-full space-y-2">
          <p className="text-base font-semibold text-[var(--color-accent)]">
            고객이 가진 물건까지 아는 AI
          </p>
          <p className="text-base text-[var(--color-text)]/80 leading-relaxed text-pretty">
            구매 이력뿐 아니라 지금 갖고 계신 제품의 실제 상태(컨디션)까지 근거로 상담하는
            럭셔리 클라이언텔링 서비스예요.
          </p>
        </div>
      </footer>

      {/* 화면 우측 하단 가장자리에 고정되는 부가 고지 — 클릭을 막지 않도록 pointer-events-none */}
      <p className="fixed bottom-2 right-3 sm:bottom-3 sm:right-4 max-w-[200px] text-right text-[12px] leading-snug text-[var(--color-muted)]/80 pointer-events-none z-10">
        이 화면은 실제 매장이 아니라 해커톤 데모이며, 등장하는 고객·상품 데이터는 모두 가상입니다.
      </p>
    </>
  )
}
