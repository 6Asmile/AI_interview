import { ref, nextTick } from 'vue';
import type { Ref } from 'vue';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { ElLoading, ElMessage } from 'element-plus';

type PreExportHook = () => Promise<void> | void;

export function useExport(elementRef: Ref<HTMLElement | null>, filename: string) {
  const isExporting = ref(false);

  const exportToPdf = async (preExportHook?: PreExportHook) => {
    if (!elementRef.value) {
      ElMessage.error('无法找到要导出的内容');
      return;
    }

    isExporting.value = true;
    const loadingInstance = ElLoading.service({
      lock: true,
      text: '正在准备导出内容...',
      background: 'rgba(0, 0, 0, 0.7)',
    });

    try {
      if (preExportHook) {
        await preExportHook();
      }
      
      await nextTick();
      // 给予足够的时间让所有动画和图表完成渲染
      await new Promise(resolve => setTimeout(resolve, 1000));

      loadingInstance.text.value = '正在生成 PDF 文件...';
      if (!elementRef.value) {
        throw new Error("导出目标元素已不存在。");
      }

      const canvas = await html2canvas(elementRef.value, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
        // 尝试允许跨域图片
        allowTaint: true,
      });

      const contentWidth = canvas.width;
      const contentHeight = canvas.height;

      const a4PageHeight = 297;
      const a4PageWidth = 210;

      // PDF 内部边距 (mm)
      const margin = 10;
      const pdfImgWidth = a4PageWidth - margin * 2;
      const pdfImgHeight = pdfImgWidth / contentWidth * contentHeight;

      const pdf = new jsPDF('p', 'mm', 'a4');
      const totalPdfPages = Math.ceil(pdfImgHeight / (a4PageHeight - margin * 2));

      let position = 0;

      for (let i = 0; i < totalPdfPages; i++) {
        if (i > 0) {
          pdf.addPage();
        }
        // 使用 jsPDF 更精确的 addImage 分页功能
        pdf.addImage(
          canvas.toDataURL('image/jpeg', 0.95),
          'JPEG',
          margin, // x
          margin - position, // y (负值，将整张大图向上移动)
          pdfImgWidth,
          pdfImgHeight
        );
        position += (a4PageHeight - margin * 2);
      }

      pdf.save(`${filename}.pdf`);

    } catch (error) {
      console.error("导出 PDF 失败:", error);
      ElMessage.error('导出 PDF 失败，请稍后重试。');
    } finally {
      isExporting.value = false;
      loadingInstance.close();
    }
  };

  // 移除 exportToHtml
  return {
    isExporting,
    exportToPdf,
  };
}