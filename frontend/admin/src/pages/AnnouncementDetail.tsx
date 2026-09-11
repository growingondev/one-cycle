import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface AnnouncementDetailProps {
  id: number;
  onBack: () => void;
}

const collectionStatusLabel: Record<string, string> = {
  running: '수집중',
  success: '수집완료',
  partial: '부분완료',
  failed: '수집실패',
};

// JSON 객체/배열을 화면에 안전하게 표시
const formatKeyInfo = (data: unknown): React.ReactNode => {
  if (
    data === null ||
    data === undefined ||
    data === ''
  ) {
    return '-';
  }

  if (
    typeof data === 'string' ||
    typeof data === 'number' ||
    typeof data === 'boolean'
  ) {
    return String(data);
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return '-';
    }

    return (
      <ul
        style={{
          margin: 0,
          paddingLeft: '16px',
          listStyleType: 'disc',
        }}
      >
        {data.map((item, index) => (
          <li key={index}>
            {formatKeyInfo(item)}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof data === 'object') {
    const entries = Object.entries(
      data as Record<string, unknown>
    );

    if (entries.length === 0) {
      return '-';
    }

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        {entries.map(([key, value]) => (
          <div key={key}>
            <strong
              style={{
                color: '#4b5563',
                fontSize: '13px',
              }}
            >
              {key}:
            </strong>

            <div
              style={{
                marginTop: '2px',
                color: 'var(--text)',
              }}
            >
              {formatKeyInfo(value)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return '-';
};

export default function AnnouncementDetail({
  id,
  onBack,
}: AnnouncementDetailProps) {
  const navigate = useNavigate();

  const [detail, setDetail] = useState<any>(null);
  const [isReCollecting, setIsReCollecting] =
    useState(false);

  useEffect(() => {
    const controller = new AbortController();

    const fetchDetail = async () => {
      try {
        const res = await fetch(
          `/api/admin/announcements/${id}`,
          {
            credentials: 'include',
            signal: controller.signal,
          }
        );

        if (res.status === 401) {
          navigate('/');
          return;
        }

        if (res.status === 404) {
          alert('해당 공고가 없습니다.');
          onBack();
          return;
        }

        if (!res.ok) {
          alert(
            '상세 정보를 불러오는 중 서버 오류가 발생했습니다.'
          );
          onBack();
          return;
        }

        const data = await res.json();

        setDetail(data);
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return;
        }

        alert('네트워크 오류가 발생했습니다.');
        onBack();
      }
    };

    fetchDetail();

    return () => {
      controller.abort();
    };
  }, [id, navigate, onBack]);

  const handleReCollect = async () => {
    try {
      setIsReCollecting(true);

      const res = await fetch(
        `/api/admin/announcements/${id}/recollect`,
        {
          method: 'POST',
          credentials: 'include',
        }
      );

      if (res.status === 401) {
        navigate('/');
        return;
      }

      if (!res.ok) {
        alert(
          '서버 오류로 인해 재수집 요청에 실패했습니다.'
        );
        return;
      }

      alert('재수집 요청이 완료되었습니다.');
    } catch {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsReCollecting(false);
    }
  };

  if (!detail) {
    return (
      <main className="content">
        <div
          style={{
            padding: '40px',
            textAlign: 'center',
          }}
        >
          불러오는 중...
        </div>
      </main>
    );
  }

  return (
    <main className="content">
      <div
        className="page-head"
        style={{ marginBottom: '24px' }}
      >
        <div>
          <h1
            style={{
              fontSize: '24px',
              margin: '0 0 6px',
            }}
          >
            공고 상세
          </h1>

          <p
            style={{
              margin: 0,
              color: 'var(--muted)',
              fontSize: '14px',
            }}
          >
            공고 내용을 확인하고 개별 재수집을 진행할 수
            있습니다.
          </p>
        </div>

        <div
          style={{
            display: 'flex',
            gap: '8px',
          }}
        >
          <button
            className="btn btn-outline"
            onClick={onBack}
          >
            ← 목록으로
          </button>

          <button
            className="btn btn-outline"
            onClick={handleReCollect}
            disabled={isReCollecting}
          >
            {isReCollecting
              ? '요청 중...'
              : '↻ 개별 재수집'}
          </button>
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: '28px 32px',
          marginBottom: '20px',
        }}
      >
        <h2
          style={{
            margin: '0 0 12px',
            fontSize: '22px',
            color: 'var(--text)',
            fontWeight: 800,
          }}
        >
          {detail.title || '-'}
        </h2>

        <div
          style={{
            color: 'var(--muted)',
            fontSize: '14px',
          }}
        >
          {detail.region || '-'} · 공고유형:{' '}
          {detail.notice_type || '-'} · 식별 ID:{' '}
          {detail.id}
        </div>

        {detail.detail_url && (
          <div style={{ marginTop: '12px' }}>
            <a
              href={detail.detail_url}
              target="_blank"
              rel="noreferrer"
              style={{
                color: 'var(--blue)',
                fontWeight: 700,
                fontSize: '14px',
              }}
            >
              🔗 원본 공고 바로가기
            </a>
          </div>
        )}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: '20px',
          marginBottom: '20px',
        }}
      >
        <div
          className="card"
          style={{
            padding: 0,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '16px 24px',
              borderBottom: '1px solid var(--line)',
              fontWeight: 800,
              fontSize: '15px',
            }}
          >
            📋 주요 정보
          </div>

          <div style={{ padding: '8px 0' }}>
            {[
              {
                label: '공고 상태',
                value:
                  detail.announcement_status || '-',
              },
              {
                label: '수집 상태',
                value:
                  collectionStatusLabel[
                    detail.collection_status
                  ] ||
                  detail.collection_status ||
                  '-',
              },
              {
                label: '접수 기간',
                value: formatKeyInfo(
                  detail.key_information
                    ?.application_period
                ),
              },
              {
                label: '신청 자격',
                value: formatKeyInfo(
                  detail.key_information?.eligibility
                ),
              },
              {
                label: '제출 서류',
                value: formatKeyInfo(
                  detail.key_information
                    ?.required_documents
                ),
              },
              {
                label: '문의처',
                value: formatKeyInfo(
                  detail.key_information
                    ?.contact_information
                ),
              },
              {
                label: '연결된 문서 수',
                value: `${
                  detail.document_count ?? 0
                }건`,
              },
            ].map((row, index) => (
              <div
                key={index}
                style={{
                  display: 'grid',
                  gridTemplateColumns:
                    '120px 1fr',
                  padding: '12px 24px',
                  borderBottom:
                    '1px solid #f8f9fc',
                  fontSize: '14px',
                }}
              >
                <span
                  style={{
                    color: 'var(--muted)',
                    fontWeight: 700,
                  }}
                >
                  {row.label}
                </span>

                <div
                  style={{
                    fontWeight: 500,
                    color: 'var(--text)',
                    lineHeight: '1.6',
                  }}
                >
                  {row.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}