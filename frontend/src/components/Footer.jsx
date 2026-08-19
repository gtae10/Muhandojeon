export default function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-surface)] px-4 sm:px-6 py-8">
      <div className="max-w-[620px] mx-auto w-full space-y-2">
        <p className="text-base font-semibold text-[var(--color-accent)]">
          고객을 아는 AI가 아니라, 고객의 물건을 아는 AI
        </p>
        <p className="text-base text-[var(--color-text)]/80 leading-relaxed text-pretty">
          구매 이력뿐 아니라 지금 갖고 계신 제품의 실제 상태(컨디션)까지 근거로 상담하는
          럭셔리 클라이언텔링 서비스예요. 이 화면은 실제 매장이 아니라 해커톤 데모이며,
          등장하는 고객·상품 데이터는 모두 가상입니다.
        </p>
      </div>
    </footer>
  )
}
