import { useEffect, useMemo, useState } from 'react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

function getVisiblePageCount() {
  if (window.innerWidth <= 560) return 5;
  if (window.innerWidth <= 900) return 7;

  return 10;
}

export default function Pagination({
  currentPage,
  totalPages,
  onPageChange,
}: PaginationProps) {
  const [visiblePageCount, setVisiblePageCount] = useState(
    getVisiblePageCount
  );

  useEffect(() => {
    const handleResize = () => {
      setVisiblePageCount(getVisiblePageCount());
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const pageNumbers = useMemo(() => {
    const safeTotalPages = Math.max(totalPages, 1);
    const safeCurrentPage = Math.min(
      Math.max(currentPage, 1),
      safeTotalPages
    );

    let startPage = Math.max(
      1,
      safeCurrentPage - Math.floor(visiblePageCount / 2)
    );

    const endPage = Math.min(
      safeTotalPages,
      startPage + visiblePageCount - 1
    );

    if (endPage - startPage + 1 < visiblePageCount) {
      startPage = Math.max(
        1,
        endPage - visiblePageCount + 1
      );
    }

    return Array.from(
      { length: endPage - startPage + 1 },
      (_, index) => startPage + index
    );
  }, [currentPage, totalPages, visiblePageCount]);

  if (totalPages <= 1) {
    return null;
  }

  return (
    <nav className="pagination" aria-label="페이지 이동">
      <button
        type="button"
        className="pagination-direction"
        aria-label="이전 페이지"
        disabled={currentPage === 1}
        onClick={() => onPageChange(currentPage - 1)}
      >
        ‹
      </button>

      {pageNumbers.map((pageNumber) => (
        <button
          type="button"
          key={pageNumber}
          className={pageNumber === currentPage ? 'active' : ''}
          aria-current={
            pageNumber === currentPage ? 'page' : undefined
          }
          onClick={() => onPageChange(pageNumber)}
        >
          {pageNumber}
        </button>
      ))}

      <button
        type="button"
        className="pagination-direction"
        aria-label="다음 페이지"
        disabled={currentPage === totalPages}
        onClick={() => onPageChange(currentPage + 1)}
      >
        ›
      </button>
    </nav>
  );
}