export function IntroScreen({ go }: { go: (s: any) => void }) {
  return (
    <div className="relative w-full min-h-screen bg-white flex justify-center items-start overflow-x-hidden">
      <div className="relative w-full max-w-[1400px]">
        <img 
          src="/image.png" 
          alt="LH 청약플러스 메인화면" 
          className="w-full h-auto block" 
        />
        
        {/* 1. 'AI 도우미 열기' 버튼 영역 (위치 우측으로 이동, 크기 최적화) */}
        <button 
          onClick={() => go("list")}
          className="absolute cursor-pointer z-10 rounded-3xl hover:bg-blue-400/30 transition-colors"
          style={{
            top: "69.5%",   // 세로 위치 미세 조정
            right: "3.5%",  // 우측으로 이동 (5% -> 3.5%)
            width: "10%",   // 너비 축소 (12% -> 10%)
            height: "4.5%"  // 높이 축소
          }}
          title="AI 도우미 열기"
          aria-label="AI 도우미 열기"
        />
        
        {/* 2. 하단 돌고래 아이콘 영역 (위치 우측으로 이동, 동그랗게 크기 최적화) */}
        <button 
          onClick={() => go("list")}
          className="absolute cursor-pointer z-10 rounded-full hover:bg-blue-400/30 transition-colors"
          style={{
            bottom: "4%",     // 세로 위치 미세 조정
            right: "3.2%",    // 우측으로 이동 (5% -> 3.2%)
            width: "6.5%",    // 너비 축소
            height: "9%"      // 높이 축소
          }}
          title="AI 도우미 열기"
        />
      </div>
    </div>
  );
}