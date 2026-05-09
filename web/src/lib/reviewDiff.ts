export type ParsedDiffLineKind = 'context' | 'add' | 'remove' | 'note';

export type ParsedDiffLine = {
  kind: ParsedDiffLineKind;
  oldLineNumber: number | null;
  newLineNumber: number | null;
  text: string;
};

export type ParsedDiffHunk = {
  id: string;
  header: string;
  lines: ParsedDiffLine[];
};

export type ParsedDiffFile = {
  id: string;
  oldPath: string | null;
  newPath: string | null;
  displayPath: string;
  additions: number;
  deletions: number;
  isNew: boolean;
  isDeleted: boolean;
  hunks: ParsedDiffHunk[];
};

export type ParsedUnifiedDiff = {
  files: ParsedDiffFile[];
};

type MutableParsedDiffFile = ParsedDiffFile;

function normalizePath(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed === '/dev/null') {
    return null;
  }
  if (trimmed.startsWith('a/') || trimmed.startsWith('b/')) {
    return trimmed.slice(2);
  }
  return trimmed;
}

function buildDisplayPath(file: MutableParsedDiffFile): string {
  if (file.oldPath && file.newPath && file.oldPath !== file.newPath) {
    return `${file.oldPath} → ${file.newPath}`;
  }
  return file.newPath ?? file.oldPath ?? 'Unknown file';
}

function createFile(index: number): MutableParsedDiffFile {
  return {
    id: `diff-file-${index}`,
    oldPath: null,
    newPath: null,
    displayPath: 'Unknown file',
    additions: 0,
    deletions: 0,
    isNew: false,
    isDeleted: false,
    hunks: [],
  };
}

export function parseUnifiedDiff(rawDiff: string): ParsedUnifiedDiff {
  if (!rawDiff.trim()) {
    return { files: [] };
  }

  const files: MutableParsedDiffFile[] = [];
  const lines = rawDiff.replace(/\r\n/g, '\n').split('\n');

  let fileIndex = 0;
  let hunkIndex = 0;
  let currentFile: MutableParsedDiffFile | null = null;
  let currentHunk: ParsedDiffHunk | null = null;
  let oldLineNumber = 0;
  let newLineNumber = 0;

  const commitFile = () => {
    if (!currentFile) {
      return;
    }
    currentFile.displayPath = buildDisplayPath(currentFile);
    files.push(currentFile);
    currentFile = null;
    currentHunk = null;
  };

  const ensureFile = () => {
    if (!currentFile) {
      currentFile = createFile(fileIndex);
      fileIndex += 1;
      hunkIndex = 0;
    }
    return currentFile;
  };

  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      commitFile();
      const nextFile = createFile(fileIndex);
      fileIndex += 1;
      hunkIndex = 0;
      const match = /^diff --git a\/(.+) b\/(.+)$/.exec(line);
      if (match) {
        nextFile.oldPath = match[1];
        nextFile.newPath = match[2];
      }
      currentFile = nextFile;
      currentHunk = null;
      continue;
    }

    const file = ensureFile();

    if (line.startsWith('new file mode ')) {
      file.isNew = true;
      continue;
    }

    if (line.startsWith('deleted file mode ')) {
      file.isDeleted = true;
      continue;
    }

    if (line.startsWith('rename from ')) {
      file.oldPath = normalizePath(line.slice('rename from '.length));
      continue;
    }

    if (line.startsWith('rename to ')) {
      file.newPath = normalizePath(line.slice('rename to '.length));
      continue;
    }

    if (line.startsWith('--- ')) {
      file.oldPath = normalizePath(line.slice(4));
      continue;
    }

    if (line.startsWith('+++ ')) {
      file.newPath = normalizePath(line.slice(4));
      continue;
    }

    if (line.startsWith('@@ ')) {
      const hunkMatch = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
      oldLineNumber = hunkMatch ? Number(hunkMatch[1]) : 0;
      newLineNumber = hunkMatch ? Number(hunkMatch[3]) : 0;
      currentHunk = {
        id: `${file.id}-hunk-${hunkIndex}`,
        header: line,
        lines: [],
      };
      hunkIndex += 1;
      file.hunks.push(currentHunk);
      continue;
    }

    if (!currentHunk) {
      continue;
    }

    if (line.startsWith('+') && !line.startsWith('+++')) {
      currentHunk.lines.push({
        kind: 'add',
        oldLineNumber: null,
        newLineNumber,
        text: line.slice(1),
      });
      file.additions += 1;
      newLineNumber += 1;
      continue;
    }

    if (line.startsWith('-') && !line.startsWith('---')) {
      currentHunk.lines.push({
        kind: 'remove',
        oldLineNumber,
        newLineNumber: null,
        text: line.slice(1),
      });
      file.deletions += 1;
      oldLineNumber += 1;
      continue;
    }

    if (line.startsWith(' ')) {
      currentHunk.lines.push({
        kind: 'context',
        oldLineNumber,
        newLineNumber,
        text: line.slice(1),
      });
      oldLineNumber += 1;
      newLineNumber += 1;
      continue;
    }

    currentHunk.lines.push({
      kind: 'note',
      oldLineNumber: null,
      newLineNumber: null,
      text: line,
    });
  }

  commitFile();

  return { files };
}
