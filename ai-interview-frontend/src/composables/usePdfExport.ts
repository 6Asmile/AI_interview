import { ref } from 'vue';
import type { Ref } from 'vue';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { ElLoading, ElMessage } from 'element-plus';

export function usePdfExport(elementRef: Ref<HTMLElement | null>, filename: string) {
  const isExporting = ref(false);

  const exportToPdf = async () => {
    if (!elementRef.value) {
      ElMessage.error('无法找到要导出的内容');
      return;
    }

    isExporting.value = true;
    const loadingInstance = ElLoading.service({
      lock: true,
      text: '正在生成 PDF 文件，请稍候...',
      background: 'rgba(0, 0, 0, 0.7)',
    });

    try {
      const canvas = await html2canvas(elementRef.value, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
      });
      
      const imgData = canvas.toDataURL('image/jpeg', 0.95);
      
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pdfWidth = pdf.internal.pageSize.getWidth();
      
      // [核心修正] 移除未使用的 pdfHeight 变量
      // const pdfHeight = pdf.internal.pageSize.getHeight(); 
      
      const imgWidth = canvas.width;
      const imgHeight = canvas.height;
      
      const ratio = imgWidth / imgHeight;
      const imgHeightOnPdf = (pdfWidth - 20) / ratio;
      let position = 10;

      pdf.addImage(imgData, 'JPEG', 10, position, pdfWidth - 20, imgHeightOnPdf);
      
      pdf.save(`${filename}.pdf`);

    } catch (error) {
      console.error("导出 PDF 失败:", error);
      ElMessage.error('导出 PDF 失败，请稍后重试。');
    } finally {
      isExporting.value = false;
      loadingInstance.close();
    }
  };

  return {
    isExporting,
    exportToPdf,
  };
}