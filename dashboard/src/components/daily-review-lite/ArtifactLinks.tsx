import type { DailyReviewLiteArtifactDescriptor } from '../../api/types';

type ArtifactLinksProps = {
  artifacts: DailyReviewLiteArtifactDescriptor[];
};

export function ArtifactLinks({ artifacts }: ArtifactLinksProps) {
  if (artifacts.length === 0) {
    return <p>No artifacts available.</p>;
  }

  return (
    <ul>
      {artifacts.map((artifact) => (
        <li key={artifact.key}>
          {artifact.available ? <a href={artifact.url}>{artifact.label}</a> : <span>{artifact.label}</span>}
          <span> ({artifact.kind})</span>
        </li>
      ))}
    </ul>
  );
}
