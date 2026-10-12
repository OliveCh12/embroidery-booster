export const ACCEPTED_FILES = ".svg,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tif,.tiff,.pdf,.eps,.ps,.ai";

const IMAGE_EXTENSIONS: Record<string, string> = {
  "image/svg+xml": "svg", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
  "image/bmp": "bmp", "image/gif": "gif", "image/tiff": "tiff",
};

export function clipboardFile(data: {
  files: ArrayLike<File>; items: ArrayLike<Pick<DataTransferItem, "kind" | "getAsFile">>;
}): File | null {
  let file: File | null = null;
  for (const item of Array.from(data.items)) {
    if (item.kind === "file") file = item.getAsFile();
    if (file) break;
  }
  file ??= data.files[0] ?? null;
  if (!file) return null;
  const extension = IMAGE_EXTENSIONS[file.type.toLowerCase()];
  if (!extension || /\.[^.]+$/.test(file.name)) return file;
  return new File([file], `${file.name || "image-collee"}.${extension}`, {
    type: file.type, lastModified: file.lastModified,
  });
}
