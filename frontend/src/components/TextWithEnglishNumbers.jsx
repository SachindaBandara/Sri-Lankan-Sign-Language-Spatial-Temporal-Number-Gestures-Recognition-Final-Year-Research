export default function TextWithEnglishNumbers({ text }) {
  return text.split(/(\d+(?:[.,]\d+)*)/g).map((segment, index) =>
    /\d/.test(segment)
      ? <span className="english-font" key={index}>{segment}</span>
      : segment
  );
}
